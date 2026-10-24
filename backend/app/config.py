from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import STRATEGIES, document

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
POLICY_PATH = Path(os.getenv('POLICY_PATH', str(DATA / 'validadores_antecipe.json')))
STOCK_PATH = DATA / 'estoque_antecipe.csv'
DB_PATH = Path(os.getenv('DB_PATH', str(DATA / 'estoque.sqlite3')))


class Fundo(BaseModel):
    nome: str
    cnpj: str

    @field_validator('cnpj')
    @classmethod
    def normalize(cls, value: str) -> str:
        result = document(value)
        if len(result) != 14:
            raise ValueError('Fundo deve ter CNPJ')
        return result


class Validator(BaseModel):
    codigo: str
    ativo: bool
    parametros: dict[str, Any] = Field(default_factory=dict)


class Pricing(BaseModel):
    metodo: str
    taxa_mensal_percentual: Decimal = Field(ge=0)
    base_dias: int = Field(gt=0)

    @field_validator('metodo')
    @classmethod
    def method(cls, value: str) -> str:
        if value not in STRATEGIES:
            raise ValueError('Método de precificação não implementado')
        return value


class Policy(BaseModel):
    model_config = ConfigDict(extra='allow')
    fundo: Fundo
    validadores: list[Validator]
    precificacao: Pricing


def load_policy() -> dict:
    if not POLICY_PATH.is_file():
        raise ValueError(f'Política oficial ausente: {POLICY_PATH}. Forneça validadores_antecipe.json; não há dados substitutos.')
    policy = Policy.model_validate(json.loads(POLICY_PATH.read_text(), parse_float=Decimal)).model_dump()
    required = {
        'SITUACAO_CADASTRAL_SACADO': 'situacoes_aceitas',
        'TIPO_RECEBIVEL': 'tipos_aceitos', 'VALOR_MINIMO': 'valor_minimo',
        'PRAZO_MAXIMO': 'prazo_maximo_dias', 'PRAZO_MINIMO': 'prazo_minimo_dias',
        'CONCENTRACAO_MAXIMA_SACADO': 'percentual_maximo',
        'CONCENTRACAO_MAXIMA_CEDENTE': 'percentual_maximo',
    }
    for rule in policy['validadores']:
        key = required.get(rule['codigo'])
        if not rule['ativo'] or not key:
            continue
        value = rule['parametros'].get(key)
        if key in ('situacoes_aceitas', 'tipos_aceitos'):
            if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                raise ValueError(f'{key} deve ser uma lista de textos não vazia')
        else:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0:
                raise ValueError(f'{key} deve ser não negativo e finito')
            if key.endswith('_dias') and number != number.to_integral_value():
                raise ValueError(f'{key} deve ser inteiro')
            if key == 'percentual_maximo' and number > 100:
                raise ValueError('percentual_maximo deve ser de 0 a 100')
    return policy


def reference_date() -> date:
    return date.fromisoformat(os.environ['DATA_REFERENCIA']) if os.getenv('DATA_REFERENCIA') else date(2026, 10, 22)


def upload_limit_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
