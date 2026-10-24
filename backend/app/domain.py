from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol

CENT = Decimal('0.01')
HEADERS = 'NOME_FUNDO DOC_FUNDO NOME_CEDENTE DOC_CEDENTE NOME_SACADO DOC_SACADO NU_DOCUMENTO TIPO_RECEBIVEL VALOR_NOMINAL DATA_VENCIMENTO_ORIGINAL DATA_AQUISICAO'.split()


def digits(value: str) -> str:
    return re.sub(r'\D', '', value)


def document(value: str) -> str:
    if not re.fullmatch(r'[\d./\-\s]+', value or ''):
        raise ValueError('use CPF ou CNPJ numérico, com ou sem pontuação')
    result = digits(value)
    if len(result) not in (11, 14):
        raise ValueError('informe 11 dígitos para CPF ou 14 para CNPJ')
    return result


def valid_document(value: str) -> bool:
    if len(set(value)) == 1:
        return False
    if len(value) == 11:
        weights = [list(range(10, 1, -1)), list(range(11, 1, -1))]
    elif len(value) == 14:
        weights = [[5,4,3,2,9,8,7,6,5,4,3,2], [6,5,4,3,2,9,8,7,6,5,4,3,2]]
    else:
        return False
    base = value[:-2]
    for weight in weights:
        remainder = sum(int(n) * w for n, w in zip(base, weight)) % 11
        base += str(0 if remainder < 2 else 11 - remainder)
    return base == value


def normalized_number(value: str) -> str:
    result = re.sub(r'[^A-Z0-9]', '', value.strip().upper())
    result = re.sub(r'^NF(?=\d)', '', result)
    return result.lstrip('0') or '0'


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Nota:
    linha: int
    fundo: str
    cedente: str
    doc_cedente: str
    sacado: str
    doc_sacado: str
    numero: str
    tipo: str
    valor: Decimal
    vencimento: date
    aquisicao: date

    @property
    def chave(self) -> str:
        return '|'.join((self.doc_cedente, self.tipo.casefold(), normalized_number(self.numero)))

    @property
    def raiz(self) -> str:
        return self.doc_sacado[:8] if len(self.doc_sacado) == 14 else self.doc_sacado


class FormatError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


def parse_row(row: dict[str, Any], line: int) -> Nota:
    if None in row or any(row.get(k) is None for k in HEADERS):
        raise FormatError('linha', 'Quantidade de colunas diferente do cabeçalho.')
    values: dict[str, Any] = {}
    for field in HEADERS:
        raw = row[field].strip()
        try:
            if not raw:
                raise ValueError('campo obrigatório')
            if field.startswith('DOC_'):
                values[field] = document(raw)
            elif field.startswith('DATA_'):
                if not re.fullmatch(r'\d{2}/\d{2}/\d{4}', raw):
                    raise ValueError('use dd/mm/aaaa')
                values[field] = datetime.strptime(raw, '%d/%m/%Y').date()
            elif field == 'VALOR_NOMINAL':
                if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?', raw):
                    raise ValueError('use valor positivo e até duas casas decimais, com vírgula')
                values[field] = Decimal(raw.replace('.', '').replace(',', '.'))
                if values[field] <= 0:
                    raise ValueError('o valor deve ser maior que zero')
            else:
                values[field] = raw
        except (ValueError, ArithmeticError) as error:
            raise FormatError(field, str(error)) from error
    return Nota(line, values['DOC_FUNDO'], values['NOME_CEDENTE'], values['DOC_CEDENTE'], values['NOME_SACADO'], values['DOC_SACADO'], values['NU_DOCUMENTO'], values['TIPO_RECEBIVEL'], values['VALOR_NOMINAL'], values['DATA_VENCIMENTO_ORIGINAL'], values['DATA_AQUISICAO'])


def csv_reader(content: bytes) -> csv.DictReader:
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=';')
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) != set(HEADERS):
        raise ValueError('O cabeçalho deve conter as 11 colunas do modelo, separadas por ponto e vírgula.')
    return reader


class PricingStrategy(Protocol):
    def __call__(self, nominal: Decimal, rate: Decimal, days: int, basis: int) -> Decimal: ...


def commercial(nominal: Decimal, rate: Decimal, days: int, basis: int) -> Decimal:
    return nominal * (1 - rate / 100 * Decimal(days) / basis)


def rational(nominal: Decimal, rate: Decimal, days: int, basis: int) -> Decimal:
    return nominal / (1 + rate / 100 * Decimal(days) / basis)


STRATEGIES: dict[str, PricingStrategy] = {'DESCONTO_SIMPLES': commercial, 'DESCONTO_POR_DENTRO': rational}


def price(nota: Nota, days: int, config: dict) -> tuple[Decimal, Decimal]:
    value = STRATEGIES[config['metodo']](nota.valor, Decimal(str(config['taxa_mensal_percentual'])), days, int(config['base_dias'])).quantize(CENT, rounding=ROUND_HALF_UP)
    if value < 0:
        raise ValueError('A taxa e o prazo resultam em valor líquido negativo.')
    return value, nota.valor - value
