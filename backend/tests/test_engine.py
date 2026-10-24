import copy
import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.domain import HEADERS, commercial, rational, normalized_number, valid_document
from app.engine import validate
from app.main import app
from app.providers import ProvedorSimulado, ProvedorBrasilAPI
from app.storage import Portfolio, seed, snapshot

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = date(2026, 10, 22)

@pytest.fixture
def policy():
    return config.load_policy()

@pytest.fixture
def row():
    return ['Demo', '12345678000195', 'Cedente', '45678901000104', 'Cliente', '99000001000119', '25', 'Duplicata', '1000,00', '21/11/2026', '22/10/2026']

def content(*rows):
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=';')
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return stream.getvalue().encode()

def portfolio(total='1000000'):
    return Portfolio(Decimal(total), {}, {}, set())

def run(policy, *rows, stock=None, provider=None, integrity=True):
    return validate(content(*rows), REFERENCE, policy, stock or portfolio(), provider or ProvedorSimulado(), integrity)

def codes(result):
    return {r['codigo'] for r in result['notas'][0]['motivos']}

def test_document_and_normalization():
    assert valid_document('11222333000181')
    assert valid_document('52998224725')
    assert not valid_document('00000000000000')
    assert not valid_document('11222333000180')
    assert {normalized_number(v) for v in ['25', '025', 'NF-25', ' nf.00025 ']} == {'25'}

def test_price_strategies():
    assert commercial(Decimal('1000'), Decimal('2'), 30, 30) == Decimal('980')
    assert rational(Decimal('1000'), Decimal('2'), 30, 30) == Decimal('1000') / Decimal('1.02')

def test_approval_and_rounding(policy, row):
    row[5] = '11222333000181'
    row[8] = '100,25'
    second = row.copy(); second[6] = '26'
    result = run(policy, row, second)
    assert result['lote']['aprovadas'] == 2
    assert result['notas'][0]['valor_liquido'] == '98.25'
    assert result['lote']['total_a_receber'] == '196.50'
    assert result['lote']['desconto_total'] == '4.00'

@pytest.mark.parametrize('days,expected', [(0,True),(180,True),(181,False),(-1,False)])
def test_day_boundaries(policy, row, days, expected):
    from datetime import timedelta
    row[5] = '11222333000181'
    row[9] = (REFERENCE + timedelta(days=days)).strftime('%d/%m/%Y')
    assert (run(policy, row)['notas'][0]['status'] == 'APROVADA') == expected

@pytest.mark.parametrize('value,expected', [('99,99',False),('100,00',True)])
def test_minimum(policy, row, value, expected):
    row[5] = '11222333000181'; row[8] = value
    assert (run(policy, row)['notas'][0]['status'] == 'APROVADA') == expected

def test_all_reasons_no_pricing(policy, row):
    row[5] = '11222333000180'; row[8] = '50,00'; row[7] = 'Cheque'; row[9] = '21/10/2026'
    result = run(policy, row)
    assert {'CNPJ_SACADO_VALIDO','SITUACAO_CADASTRAL_SACADO','VALOR_MINIMO','TIPO_RECEBIVEL','NAO_VENCIDA'} <= codes(result)
    assert result['notas'][0]['valor_liquido'] is None
    assert result['lote']['total_a_receber'] == '0.00'

def test_cpf(policy, row):
    row[5] = '52998224725'
    result = run(policy, row)
    assert result['notas'][0]['status'] == 'APROVADA'
    assert any('pessoa física' in o for o in result['notas'][0]['observacoes'])
    row[5] = '52998224726'
    assert 'CNPJ_SACADO_VALIDO' in codes(run(policy,row))

def test_provider_failure_and_status(policy, row):
    row[5] = '11222333000181'
    for status in (None,'BAIXADA'):
        assert 'SITUACAO_CADASTRAL_SACADO' in codes(run(policy,row,provider=ProvedorSimulado({row[5]:status})))

def test_policy_toggle_unknown_and_messages(policy, row, caplog):
    row[5] = '11222333000181'
    minimum = next(r for r in policy['validadores'] if r['codigo'] == 'PRAZO_MINIMO')
    minimum.update(ativo=True, parametros={'prazo_minimo_dias':31})
    policy['validadores'].append(dict(codigo='NOVA_REGRA', ativo=True, parametros={}))
    result = run(policy,row)
    assert 'PRAZO_MINIMO' in codes(result)
    assert '31 dias' in result['notas'][0]['motivos'][0]['mensagem']
    assert result['avisos'] and 'NOVA_REGRA' in caplog.text

def test_concentration_order_exact_denominator(policy,row):
    row[5] = '11222333000181'; row[8] = '100,00'
    stock = portfolio('1000')
    second = row.copy(); second[6] = '26'
    result = run(policy,row,second,stock=stock)
    assert [n['status'] for n in result['notas']] == ['APROVADA','RECUSADA']
    assert result['notas'][1]['motivos'][0]['codigo'] == 'CONCENTRACAO_MAXIMA_SACADO'
    # Candidate is in numerator, NOT in denominator: 101/1000 > 10%.
    row[8] = '101,00'
    assert 'CONCENTRACAO_MAXIMA_SACADO' in codes(run(policy,row,stock=stock))

def test_rejected_does_not_consume_concentration(policy,row):
    row[5] = '11222333000181'; row[8] = '100,00'
    rejected = row.copy(); rejected[6] = '24'; rejected[7] = 'Cheque'
    result = run(policy,rejected,row,stock=portfolio('1000'))
    assert [n['status'] for n in result['notas']] == ['RECUSADA','APROVADA']

def test_empty_portfolio_and_cedente_toggle(policy,row):
    row[5] = '11222333000181'
    result = run(policy,row,stock=portfolio('0'))
    assert result['notas'][0]['status'] == 'APROVADA'
    assert any('Carteira vazia' in o for o in result['notas'][0]['observacoes'])
    rule = next(r for r in policy['validadores'] if r['codigo'] == 'CONCENTRACAO_MAXIMA_CEDENTE')
    rule['ativo'] = True
    assert 'CONCENTRACAO_MAXIMA_CEDENTE' in codes(run(policy,row,stock=portfolio('10000')))

def test_duplicate_stock_batch_toggle(policy,row):
    row[5] = '11222333000181'
    second = row.copy(); second[6] = 'NF-025'
    result = run(policy,row,second)
    assert result['notas'][1]['motivos'][0]['codigo'] == 'DUPLICIDADE'
    stock = portfolio(); stock.chaves.add('45678901000104|duplicata|25')
    assert 'DUPLICIDADE' in codes(run(policy,row,stock=stock))
    assert run(policy,row,second,stock=stock,integrity=False)['lote']['aprovadas'] == 2

@pytest.mark.parametrize('index,value', [(8,'abc'),(8,'NaN'),(9,'2026-11-21'),(5,'123'),(5,'abcdefghijk'),(8,'-10,00'),(8,'1,234')])
def test_malformed_row_isolated(policy,row,index,value):
    good = row.copy(); good[5] = '11222333000181'; good[6] = '26'
    row[index] = value
    result = run(policy,row,good)
    assert result['lote']['erros'] == 1
    assert result['lote']['aprovadas'] == 1
    assert result['notas'][0]['motivos'][0]['campo'] == HEADERS[index]

def test_stock_idempotent_filter_and_rollback(tmp_path,row):
    path = tmp_path/'stock.csv'; db = tmp_path/'stock.db'
    second = row.copy(); second[1] = '11222333000181'; second[8] = '9000,00'; second[6] = '50'
    path.write_bytes(content(row,second))
    assert seed(path,db) == seed(path,db) == 2
    result = snapshot(db,row[1])
    assert result.total == Decimal('1000')
    assert len(result.chaves) == 2
    row[8] = 'oops'; path.write_bytes(content(row))
    with pytest.raises(ValueError): seed(path,db)
    assert snapshot(db,second[1]).total == Decimal('9000')

def test_api_upload_errors_and_live_policy(tmp_path,monkeypatch,row,policy):
    import json
    policy_path = tmp_path/'policy.json'
    policy_path.write_text(json.dumps(policy,default=str))
    monkeypatch.setattr(config,'POLICY_PATH',policy_path)
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'stock.db')
    prepare_stock(tmp_path, monkeypatch)
    monkeypatch.setenv('DATA_REFERENCIA','2026-10-22')
    row[5] = '11222333000181'
    with TestClient(app) as client:
        assert client.get('/api/v1/saude').status_code == 200
        assert client.get('/api/v1/regras').json()['data_referencia_padrao'] == '2026-10-22'
        response = client.post('/api/v1/validacoes',files={'arquivo':('a.csv',content(row),'text/csv')})
        assert response.status_code == 200, response.text
        assert response.json()['lote']['aprovadas'] == 1
        next(r for r in policy['validadores'] if r['codigo']=='VALOR_MINIMO')['parametros']['valor_minimo'] = 2000
        policy_path.write_text(json.dumps(policy,default=str))
        assert client.post('/api/v1/validacoes',files={'arquivo':('a.csv',content(row),'text/csv')}).json()['lote']['recusadas'] == 1
        for filename,body,status in [('a.txt',b'abc',415),('a.csv',b'abc',422),('a.csv',b'\xff',422),('a.csv',content(),422)]:
            r = client.post('/api/v1/validacoes',files={'arquivo':(filename,body,'text/csv')})
            assert r.status_code == status
            assert r.headers['content-type'].startswith('application/problem+json')
        assert client.post('/api/v1/validacoes',files={'arquivo':('a.csv',content(row),'text/csv')},data={'data_referencia':'x'}).status_code == 422
        monkeypatch.setenv('MAX_UPLOAD_MB','1')
        assert client.post('/api/v1/validacoes',files={'arquivo':('a.csv',b'x'*1100000,'text/csv')}).status_code == 413

def test_public_provider_cache_retry(monkeypatch):
    import app.providers as providers
    calls = []
    def fail(*args,**kwargs):
        calls.append(1)
        raise TimeoutError()
    monkeypatch.setattr(providers,'urlopen',fail)
    provider = ProvedorBrasilAPI(timeout=.01,retries=1)
    assert provider.consultar('11222333000181') is None
    assert provider.consultar('11222333000181') is None
    assert len(calls) == 2


def test_upload_above_old_limit(tmp_path, monkeypatch, row):
    """A valid ~20 MB file must reach the engine; don't generate 100k responses here."""
    monkeypatch.delenv('MAX_UPLOAD_MB', raising=False)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'stock.db')
    prepare_stock(tmp_path, monkeypatch)
    row[5] = '11222333000181'
    # Space padding in a text field is valid CSV and does not alter the note.
    # Keep individual fields below the CSV parser's default size limit.
    padded = row.copy(); padded[2] = 'Cedente' + ' ' * 100000
    payload = content(*[padded for _ in range(210)])
    assert 19 * 1024 * 1024 < len(payload) < 50 * 1024 * 1024
    with TestClient(app) as client:
        assert client.get('/api/v1/regras').json()['max_upload_bytes'] == 50 * 1024 * 1024
        response = client.post('/api/v1/validacoes', files={'arquivo': ('estoque.csv', payload, 'text/csv')}, data={'data_referencia': '2026-10-22'})
        assert response.status_code == 200, response.text[:500]
        assert response.json()['lote']['total_notas'] == 210
        monkeypatch.setenv('MAX_UPLOAD_MB', '1')
        assert client.get('/api/v1/regras').json()['max_upload_bytes'] == 1024 * 1024
        rejected = client.post('/api/v1/validacoes', files={'arquivo': ('estoque.csv', payload, 'text/csv')})
        assert rejected.status_code == 413
        assert '1 MB' in rejected.json()['detail']


def prepare_stock(tmp_path, monkeypatch):
    path = tmp_path / 'estoque.csv'
    path.write_bytes(content())
    monkeypatch.setattr(config, 'STOCK_PATH', path)
    seed(path, config.DB_PATH)
