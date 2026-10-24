from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from .domain import Nota, valid_document
from .providers import ProvedorSituacaoCadastral
from .storage import Portfolio
from .formatting import decimal_br, days_br


@dataclass
class ResultadoRegra:
    ok: bool
    codigo: str
    mensagem: str
    acao_sugerida: str = ''
    detalhes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Contexto:
    dias: int
    portfolio: Portfolio
    provider: ProvedorSituacaoCadastral
    aprovadas_total: Decimal = Decimal(0)
    sacados: dict[str, Decimal] = field(default_factory=dict)
    cedentes: dict[str, Decimal] = field(default_factory=dict)
    situacoes: dict[str, str | None] = field(default_factory=dict)


class Regra(Protocol):
    codigo: str
    def avaliar(self, nota: Nota, contexto: Contexto) -> ResultadoRegra: ...


class Base:
    codigo = ''
    def __init__(self, parametros: dict):
        self.p = parametros

    def result(self, ok: bool, message: str, action: str = '', **details: Any) -> ResultadoRegra:
        return ResultadoRegra(ok, self.codigo, message, action, details)


class Documento(Base):
    codigo = 'CNPJ_SACADO_VALIDO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        cpf = len(n.doc_sacado) == 11
        return self.result(valid_document(n.doc_sacado), ('CPF válido; a regra de CNPJ não se aplica a pessoa física.' if valid_document(n.doc_sacado) else 'O CPF do seu cliente tem dígitos verificadores inválidos.') if cpf else ('CNPJ válido.' if valid_document(n.doc_sacado) else 'O CNPJ do seu cliente tem dígitos verificadores inválidos.'), 'Confira o documento do seu cliente e envie a nota novamente.')


class Situacao(Base):
    codigo = 'SITUACAO_CADASTRAL_SACADO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        if len(n.doc_sacado) == 11:
            return self.result(True, 'Consulta de CNPJ não se aplica a pessoa física (CPF).')
        if not valid_document(n.doc_sacado):
            return self.result(False, 'Não foi possível verificar a situação cadastral do sacado (seu cliente).', 'Corrija o CNPJ e tente novamente.')
        if n.doc_sacado not in c.situacoes:
            try:
                c.situacoes[n.doc_sacado] = c.provider.consultar(n.doc_sacado)
            except Exception:
                c.situacoes[n.doc_sacado] = None
        status = c.situacoes[n.doc_sacado]
        if status is None:
            return self.result(False, 'Não foi possível verificar a situação cadastral do sacado (seu cliente).', 'Tente novamente mais tarde ou confira o cadastro do seu cliente.')
        accepted = self.p['situacoes_aceitas']
        return self.result(status in accepted, f'A situação cadastral do seu cliente é {status}. O fundo aceita: {", ".join(accepted)}.', 'Peça ao seu cliente para regularizar o cadastro antes de reenviar.')


class Tipo(Base):
    codigo = 'TIPO_RECEBIVEL'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        accepted = self.p['tipos_aceitos']
        return self.result(n.tipo in accepted, f'O tipo {n.tipo} não é aceito. O fundo aceita: {", ".join(accepted)}.', 'Envie uma nota de um dos tipos aceitos pelo fundo.')


class Minimo(Base):
    codigo = 'VALOR_MINIMO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        minimum = Decimal(str(self.p['valor_minimo']))
        return self.result(n.valor >= minimum, f'O valor mínimo por nota é R$ {decimal_br(minimum)}; esta nota tem R$ {decimal_br(n.valor)}.', 'Selecione uma nota com valor igual ou maior que o mínimo.')


class NaoVencida(Base):
    codigo = 'NAO_VENCIDA'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        return self.result(c.dias >= 0, f'Esta nota venceu há {days_br(abs(c.dias))}.', 'Envie uma nota que ainda não venceu; se a data estiver incorreta, corrija o arquivo.')


class Maximo(Base):
    codigo = 'PRAZO_MAXIMO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        limit = int(self.p['prazo_maximo_dias'])
        return self.result(c.dias <= limit, f'O prazo máximo aceito pelo fundo é de {days_br(limit)}; esta nota vence em {days_br(c.dias)}.', 'Reenvie quando o vencimento estiver dentro do prazo aceito.')


class PrazoMinimo(Base):
    codigo = 'PRAZO_MINIMO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        limit = int(self.p['prazo_minimo_dias'])
        return self.result(c.dias >= limit, f'O prazo mínimo aceito pelo fundo é de {days_br(limit)}; esta nota vence em {days_br(c.dias)}.', 'Escolha uma nota com vencimento mais distante.')


class Concentracao(Base):
    codigo = 'CONCENTRACAO_MAXIMA_SACADO'
    def avaliar(self, n: Nota, c: Contexto) -> ResultadoRegra:
        cedente = self.codigo.endswith('CEDENTE')
        key = n.doc_cedente if cedente else n.raiz
        current = c.portfolio.cedentes if cedente else c.portfolio.sacados
        approved = c.cedentes if cedente else c.sacados
        limit = Decimal(str(self.p['percentual_maximo']))
        denominator = c.portfolio.total + c.aprovadas_total
        numerator = current.get(key, Decimal(0)) + approved.get(key, Decimal(0)) + n.valor
        if denominator == 0:
            return self.result(True, 'Carteira vazia: limite de concentração dispensado para a primeira nota elegível.', carteira_vazia=True)
        ratio = numerator / denominator * 100
        if ratio <= limit:
            return self.result(True, '', percentual=str(ratio), limite=str(limit))
        subject = 'sua empresa' if cedente else 'seu cliente (empresas com a mesma raiz de CNPJ)'
        return self.result(False, f'A participação de {subject} seria {decimal_br(ratio)}%, acima do limite de {decimal_br(limit)}% do fundo.', 'Selecione notas de outros clientes ou consulte o fundo sobre a disponibilidade de limite.' if not cedente else 'Consulte o fundo sobre o limite disponível para sua empresa.', percentual=str(ratio), limite=str(limit))


class ConcentracaoCedente(Concentracao):
    codigo = 'CONCENTRACAO_MAXIMA_CEDENTE'


REGISTRO = {rule.codigo: rule for rule in (Documento, Situacao, Tipo, Minimo, NaoVencida, Maximo, PrazoMinimo, Concentracao, ConcentracaoCedente)}
