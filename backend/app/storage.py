from __future__ import annotations

import sqlite3
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .domain import FormatError, csv_reader, parse_row

SCHEMA = '''
CREATE TABLE IF NOT EXISTS origem (id INTEGER PRIMARY KEY CHECK(id=1), caminho TEXT, tamanho INTEGER, mtime INTEGER, sha256 TEXT);

CREATE TABLE IF NOT EXISTS estoque (
 fundo TEXT NOT NULL, cedente TEXT NOT NULL, raiz TEXT NOT NULL,
 chave TEXT NOT NULL, centavos INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fundo ON estoque(fundo);
CREATE INDEX IF NOT EXISTS idx_cedente ON estoque(cedente);
CREATE INDEX IF NOT EXISTS idx_raiz ON estoque(raiz);
CREATE INDEX IF NOT EXISTS idx_chave ON estoque(chave);
CREATE INDEX IF NOT EXISTS idx_fundo_raiz ON estoque(fundo, raiz);
CREATE INDEX IF NOT EXISTS idx_fundo_cedente ON estoque(fundo, cedente);
'''


@dataclass
class Portfolio:
    total: Decimal
    sacados: dict[str, Decimal]
    cedentes: dict[str, Decimal]
    chaves: set[str]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def snapshot(path: Path, fundo: str) -> Portfolio:
    db = connect(path)
    try:
        db.execute('BEGIN')
        total = Decimal(db.execute('SELECT COALESCE(SUM(centavos),0) FROM estoque WHERE fundo=?', (fundo,)).fetchone()[0]) / 100
        sacados = {k: Decimal(v) / 100 for k, v in db.execute('SELECT raiz,SUM(centavos) FROM estoque WHERE fundo=? GROUP BY raiz', (fundo,))}
        cedentes = {k: Decimal(v) / 100 for k, v in db.execute('SELECT cedente,SUM(centavos) FROM estoque WHERE fundo=? GROUP BY cedente', (fundo,))}
        keys = {row[0] for row in db.execute('SELECT chave FROM estoque')}
        return Portfolio(total, sacados, cedentes, keys)
    finally:
        db.close()


def seed(csv_path: Path, db_path: Path) -> int:
    if not csv_path.is_file():
        raise ValueError(f'Estoque oficial ausente: {csv_path}. Forneça o CSV e execute make seed.')
    content = csv_path.read_bytes()
    reader = csv_reader(content)
    db = connect(db_path)
    count = 0
    try:
        with db:
            db.execute('DELETE FROM estoque')
            batch = []
            for row in reader:
                try:
                    nota = parse_row(row, reader.line_num)
                except FormatError as error:
                    raise ValueError(f'Estoque, linha {reader.line_num}, {error.field}: {error}') from error
                batch.append((nota.fundo, nota.doc_cedente, nota.raiz, nota.chave, int(nota.valor * 100)))
                count += 1
                if len(batch) == 2000:
                    db.executemany('INSERT INTO estoque VALUES (?,?,?,?,?)', batch)
                    batch.clear()
            db.executemany('INSERT INTO estoque VALUES (?,?,?,?,?)', batch)
            stat = csv_path.stat()
            db.execute('INSERT OR REPLACE INTO origem VALUES (1,?,?,?,?)', (str(csv_path.resolve()), stat.st_size, stat.st_mtime_ns, hashlib.sha256(content).hexdigest()))
    finally:
        db.close()
    return count


def require_stock(csv_path: Path, db_path: Path) -> None:
    if not csv_path.is_file():
        raise ValueError(f'Estoque oficial ausente: {csv_path}. Forneça estoque_antecipe.csv e execute make seed.')
    if not db_path.is_file():
        raise ValueError('Estoque não carregado no banco. Execute make seed.')
    with sqlite3.connect(db_path) as db:
        try:
            source = db.execute('SELECT caminho,tamanho,mtime FROM origem WHERE id=1').fetchone()
        except sqlite3.OperationalError:
            source = None
    stat = csv_path.stat()
    if source != (str(csv_path.resolve()), stat.st_size, stat.st_mtime_ns):
        raise ValueError('O estoque do banco não corresponde ao CSV atual. Execute make seed para recarregar o estoque oficial.')
