"""Synthetic benchmark: 100k stock rows, 18 funds, 5k uploaded notes."""
import csv
import io
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.config import load_policy
from app.domain import HEADERS
from app.engine import validate
from app.providers import ProvedorSimulado
from app.storage import seed, snapshot

policy = load_policy()

def doc(base):
    for weights in ([5,4,3,2,9,8,7,6,5,4,3,2],[6,5,4,3,2,9,8,7,6,5,4,3,2]):
        mod = sum(int(n)*w for n,w in zip(base,weights)) % 11
        base += str(0 if mod < 2 else 11-mod)
    return base

def row(i, stock=False):
    fund = policy['fundo']['cnpj'] if not stock or i % 18 == 0 else doc(f'{30000000+i%18}0001')
    return ['Fundo',fund,'Empresa',doc(f'{40000000+i%500}0001'),'Cliente',doc(f'{50000000+i%5000}0001'),str(i+100000 if stock else i),'Duplicata','100000,00' if stock else '1000,00','21/11/2026','22/10/2026']

with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'stock.csv'; db=Path(temp)/'stock.db'
    with path.open('w',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(HEADERS)
        writer.writerows(row(i,True) for i in range(100000))
    started=perf_counter();seed(path,db);seed_seconds=perf_counter()-started
    stream=io.StringIO();writer=csv.writer(stream,delimiter=';');writer.writerow(HEADERS)
    writer.writerows(row(i) for i in range(5000))
    payload=stream.getvalue().encode()
    started=perf_counter()
    result=validate(payload,date(2026,10,22),policy,snapshot(db,policy['fundo']['cnpj']),ProvedorSimulado())
    json.dumps(result)
    elapsed=perf_counter()-started
    report={'stock_rows':100000,'funds':18,'batch_rows':5000,'approved':result['lote']['aprovadas'],'seed_seconds':round(seed_seconds,3),'validation_with_snapshot_and_json_seconds':round(elapsed,3),'under_3_seconds':elapsed<3,'provider':'simulated','synthetic':True}
    print(json.dumps(report,indent=2))
    (ROOT/'docs'/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    assert elapsed < 3, f'Performance target missed: {elapsed:.3f}s'
