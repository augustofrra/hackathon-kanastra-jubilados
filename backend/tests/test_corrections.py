import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import config
from app.domain import csv_reader, parse_row, normalized_number
from app.engine import validate
from app.formatting import decimal_br, days_br
from app.main import app
from app.providers import ProvedorSimulado
from app.rules import Concentracao, Contexto
from app.storage import seed, snapshot
from test_engine import content, portfolio, run, codes, prepare_stock, row, policy

ROOT = Path(__file__).resolve().parents[2]


def test_official_identity_and_stock():
    p = config.load_policy()
    assert p['fundo'] == {'nome': 'ANTECIPE FIDC', 'cnpj': '92234400000180'}
    assert 'demonstrativo' not in p
    reader = csv_reader(config.STOCK_PATH.read_bytes())
    assert sum(1 for _ in reader) == 100554
    assert snapshot(config.DB_PATH, p['fundo']['cnpj']).total == Decimal('53074028')


def test_missing_official_files_fail_clearly(tmp_path, monkeypatch):
    original = config.POLICY_PATH
    monkeypatch.setattr(config, 'POLICY_PATH', tmp_path / 'missing.json')
    with TestClient(app) as client:
        response = client.get('/api/v1/regras')
        assert response.status_code == 503
        assert 'Política oficial ausente' in response.json()['detail']
        monkeypatch.setattr(config, 'POLICY_PATH', original)
        monkeypatch.setattr(config, 'STOCK_PATH', tmp_path / 'missing.csv')
        response = client.get('/api/v1/regras')
        assert response.status_code == 503
        assert 'Estoque oficial ausente' in response.json()['detail']
    with pytest.raises(ValueError, match='Estoque oficial ausente'):
        seed(tmp_path / 'missing.csv', tmp_path / 'db.sqlite')


def test_old_database_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'db.sqlite')
    prepare_stock(tmp_path, monkeypatch)
    config.STOCK_PATH.write_bytes(config.STOCK_PATH.read_bytes() + b'\n')
    with TestClient(app) as client:
        response = client.get('/api/v1/saude')
        assert response.status_code == 503
        assert 'make seed' in response.json()['detail']


@pytest.mark.parametrize('value,expected', [('190,00', True), ('10000,00', True), ('10001,00', False)])
def test_concentration_message_only_on_failure(policy, row, value, expected):
    row[5] = '11222333000181'; row[8] = value
    reader = csv_reader(content(row)); n = parse_row(next(reader), 2)
    context = Contexto(30, portfolio('100000'), ProvedorSimulado())
    result = Concentracao({'percentual_maximo': 10}).avaliar(n, context)
    assert result.ok == expected
    if expected:
        assert result.mensagem == ''
        output = run(policy, row, stock=context.portfolio)
        assert not any('participação' in message for message in output['notas'][0]['observacoes'])
        assert 'CONCENTRACAO_MAXIMA_SACADO' not in codes(output)
    else:
        assert '10,00%' in result.mensagem
        assert 'acima do limite' in result.mensagem
    # Below 1%, format the displayed failure with comma when policy limit is smaller.
    row[8] = '190,00'
    reader = csv_reader(content(row)); n = parse_row(next(reader), 2)
    assert '0,19%' in Concentracao({'percentual_maximo': '0.1'}).avaliar(n, context).mensagem


def test_pt_br_and_reference_default(monkeypatch):
    assert decimal_br(Decimal('100554')) == '100.554,00'
    assert decimal_br(Decimal('0.19')) == '0,19'
    assert days_br(1) == '1 dia'
    assert days_br(-1) == '-1 dia'
    assert days_br(2) == '2 dias'
    monkeypatch.delenv('DATA_REFERENCIA', raising=False)
    assert config.reference_date() == date(2026, 10, 22)
    with TestClient(app) as client:
        assert client.get('/api/v1/regras').json()['data_referencia_padrao'] == '2026-10-22'
    monkeypatch.setenv('DATA_REFERENCIA', '2026-10-23')
    assert config.reference_date() == date(2026, 10, 23)


def test_duplicate_isolation_between_sellers_and_types(policy, row):
    row[5] = '11222333000181'
    other_seller = row.copy(); other_seller[3] = '11222333000181'
    other_type = row.copy(); other_type[7] = 'Duplicata de Serviço'
    same = row.copy(); same[6] = 'NF-00025'
    result = run(policy, row, other_seller, other_type, same)
    assert [n['status'] for n in result['notas']] == ['APROVADA', 'APROVADA', 'APROVADA', 'RECUSADA']
    stock = portfolio(); stock.chaves.add('45678901000104|duplicata|25')
    for note in (other_seller, other_type):
        assert 'DUPLICIDADE' not in codes(run(policy, note, stock=stock))
    assert 'DUPLICIDADE' in codes(run(policy, same, stock=stock))


def test_audit_real_pairs():
    import importlib.util
    spec = importlib.util.spec_from_file_location('audit', ROOT/'scripts/audit_duplicates.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    report = module.audit(config.STOCK_PATH, ROOT/'backend/tests/fixtures/estoque_anterior.csv')
    assert report['repetidas_apos_primeira_no_lote'] == 9657
    assert report['numero_original_diferente'] == 0
    assert report['coincidencias_estoque_anterior'] == 0
    assert report['coincidencias_apos_seed_oficial'] == 100554
    assert len(report['exemplos']) == 5
    for pair in report['exemplos']:
        assert len(set(pair['doc_cedente'])) == len(set(pair['tipos'])) == 1
        assert len({normalized_number(v) for v in pair['numeros_originais']}) == 1


def test_live_json_minimum_concentration_and_reference(tmp_path, monkeypatch, row, policy):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path/'db.sqlite')
    stock = row.copy(); stock[1] = policy['fundo']['cnpj']; stock[5] = '52998224725'; stock[6] = '999'; stock[8] = '100000,00'
    stock_path = tmp_path/'stock.csv'; stock_path.write_bytes(content(stock))
    monkeypatch.setattr(config, 'STOCK_PATH', stock_path)
    seed(stock_path, config.DB_PATH)
    path = tmp_path/'policy.json'
    monkeypatch.setattr(config, 'POLICY_PATH', path)
    monkeypatch.delenv('DATA_REFERENCIA', raising=False)
    def save(): path.write_text(json.dumps(policy, default=str))
    save()
    row[5] = '11222333000181'
    with TestClient(app) as client:
        def submit(reference=None):
            response = client.post('/api/v1/validacoes', files={'arquivo': ('lote.csv', content(row), 'text/csv')}, data={'data_referencia': reference} if reference else {})
            assert response.status_code == 200, response.text
            return response.json()
        assert submit()['lote']['aprovadas'] == 1
        minimum = next(r for r in policy['validadores'] if r['codigo'] == 'PRAZO_MINIMO')
        minimum['ativo'] = True; minimum['parametros']['prazo_minimo_dias'] = 31; save()
        assert 'PRAZO_MINIMO' in codes(submit())
        assert submit('2026-10-21')['lote']['aprovadas'] == 1
        minimum['ativo'] = False
        concentration = next(r for r in policy['validadores'] if r['codigo'] == 'CONCENTRACAO_MAXIMA_SACADO')
        concentration['parametros']['percentual_maximo'] = '0.5'; save()
        assert 'CONCENTRACAO_MAXIMA_SACADO' in codes(submit())
        concentration['parametros']['percentual_maximo'] = 10; save()
        assert submit()['lote']['aprovadas'] == 1
        row[8] = 'malformado'
        result = submit()
        assert result['lote']['erros'] == 1
        assert result['notas'][0]['motivos'][0]['campo'] == 'VALOR_NOMINAL'


def test_sample_twenty_rows_and_rule_coverage(policy):
    payload = (ROOT/'samples/lote_demo.csv').read_bytes()
    stock = snapshot(config.DB_PATH, policy['fundo']['cnpj'])
    result = validate(payload, date(2026,10,22), policy, stock, ProvedorSimulado())
    assert result['lote']['total_notas'] == 20
    assert result['lote']['aprovadas'] > 0
    assert result['lote']['erros'] == 1
    failures = {r['codigo'] for n in result['notas'] for r in n['motivos']}
    assert {r['codigo'] for r in policy['validadores'] if r['ativo']} | {'DUPLICIDADE', 'ERRO_DE_FORMATO'} <= failures
    for r in policy['validadores']: r['ativo'] = True
    result = validate(payload, date(2026,10,22), policy, stock, ProvedorSimulado())
    failures = {r['codigo'] for n in result['notas'] for r in n['motivos']}
    assert {'PRAZO_MINIMO', 'CONCENTRACAO_MAXIMA_CEDENTE'} <= failures
