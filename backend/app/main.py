from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import config
from .engine import validate
from .providers import ProvedorBrasilAPI, ProvedorSimulado
from .storage import snapshot, require_stock
from .schemas import ResultadoValidacao

app = FastAPI(title='Portal Antecipe', version='1.0.0', description='Validação e simulação de antecipação de recebíveis. Valores monetários são strings decimais.')
public_provider = ProvedorBrasilAPI()


class Problem(Exception):
    def __init__(self, status: int, title: str, detail: str):
        self.status, self.title, self.detail = status, title, detail


@app.exception_handler(Problem)
async def problem_handler(request, exc: Problem):
    return JSONResponse(status_code=exc.status, media_type='application/problem+json', content=dict(type='about:blank', title=exc.title, status=exc.status, detail=exc.detail, instance=request.url.path))


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    return await problem_handler(request, Problem(422, 'Dados inválidos', 'Confira os campos enviados. A data deve estar no formato AAAA-MM-DD.'))


@app.middleware('http')
async def upload_limit(request, call_next):
    limit = config.upload_limit_bytes()
    if request.url.path == '/api/v1/validacoes':
        # Guard the whole multipart body, including chunked transfers, before parsing.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit + 65536:
                return await problem_handler(request, Problem(413, 'Arquivo muito grande', f'O limite é {limit // 1024 // 1024} MB.'))
        request._body = bytes(body)
    return await call_next(request)


def current_policy():
    try:
        policy = config.load_policy()
        require_stock(config.STOCK_PATH, config.DB_PATH)
        return policy
    except (OSError, ValueError, ArithmeticError) as exc:
        raise Problem(503, 'Política indisponível', f'Confira o arquivo de política: {exc}') from exc


@app.get('/api/v1/saude')
def health():
    current_policy()
    return {'status': 'ok', 'provedor': os.getenv('PROVEDOR_CADASTRAL', 'simulado')}


@app.get('/api/v1/regras')
def policy():
    value = current_policy()
    value['max_upload_bytes'] = config.upload_limit_bytes()
    value['data_referencia_padrao'] = config.reference_date().isoformat()
    value['provedor_cadastral'] = os.getenv('PROVEDOR_CADASTRAL', 'simulado')
    value['integridade_ativa'] = os.getenv('INTEGRIDADE_ATIVA', 'true').lower() == 'true'
    return jsonable_encoder(value, custom_encoder={Decimal: str})


def execute(content, reference, policy):
    portfolio = snapshot(config.DB_PATH, policy['fundo']['cnpj'])
    provider = public_provider if os.getenv('PROVEDOR_CADASTRAL', 'simulado') == 'brasilapi' else ProvedorSimulado(policy.get('situacoes_simuladas'))
    return validate(content, reference, policy, portfolio, provider, os.getenv('INTEGRIDADE_ATIVA', 'true').lower() == 'true')


@app.post('/api/v1/validacoes', response_model=ResultadoValidacao)
async def validation(arquivo: Annotated[UploadFile, File()], data_referencia: Annotated[date | None, Form()] = None):
    if not (arquivo.filename or '').lower().endswith('.csv') or arquivo.content_type not in ('text/csv', 'application/csv', 'application/vnd.ms-excel', 'text/plain', 'application/octet-stream'):
        raise Problem(415, 'Formato não aceito', 'Envie um arquivo CSV UTF-8, separado por ponto e vírgula.')
    limit = config.upload_limit_bytes()
    content = await arquivo.read(limit + 1)
    await arquivo.close()
    if len(content) > limit:
        raise Problem(413, 'Arquivo muito grande', f'O limite é {limit // 1024 // 1024} MB.')
    try:
        result = await run_in_threadpool(execute, content, data_referencia or config.reference_date(), current_policy())
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise Problem(422, 'Não foi possível processar o arquivo', str(exc)) from exc
    if not result['lote']['total_notas']:
        raise Problem(422, 'Arquivo vazio', 'Inclua pelo menos uma nota após o cabeçalho.')
    return result
