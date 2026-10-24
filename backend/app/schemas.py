from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, Field


class Motivo(BaseModel):
    codigo: str
    mensagem: str
    acao_sugerida: str
    campo: str | None = None
    detalhes: dict[str, Any] = Field(default_factory=dict)


class ResultadoNota(BaseModel):
    linha: int
    cedente: str | None
    sacado: str | None
    numero_documento: str | None
    tipo: str | None
    valor_nominal: str | None
    vencimento: date | None
    dias: int | None
    status: Literal['APROVADA', 'RECUSADA', 'ERRO_DE_FORMATO']
    valor_liquido: str | None
    desconto: str | None
    motivos: list[Motivo]
    observacoes: list[str]


class Lote(BaseModel):
    id: str
    data_referencia: date
    total_notas: int
    aprovadas: int
    recusadas: int
    erros: int
    valor_nominal_total: str
    total_a_receber: str
    desconto_total: str


class ResumoRecusa(BaseModel):
    codigo: str
    quantidade: int
    mensagem_resumo: str


class ResultadoValidacao(BaseModel):
    lote: Lote
    notas: list[ResultadoNota]
    resumo_recusas: list[ResumoRecusa]
    avisos: list[str]
