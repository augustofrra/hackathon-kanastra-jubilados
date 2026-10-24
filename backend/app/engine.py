from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

from .domain import FormatError, csv_reader, money, parse_row, price
from .providers import ProvedorSituacaoCadastral
from .rules import Contexto, REGISTRO
from .storage import Portfolio


def validate(content: bytes, reference: date, policy: dict, portfolio: Portfolio, provider: ProvedorSituacaoCadastral, integrity: bool = True) -> dict:
    reader = csv_reader(content)
    rules = []
    warnings = []
    for config in policy['validadores']:
        if not config['ativo']:
            continue
        cls = REGISTRO.get(config['codigo'])
        if cls is None:
            warning = f"Validador desconhecido ignorado: {config['codigo']}"
            warnings.append(warning)
            logging.warning(warning)
        else:
            rules.append(cls(config.get('parametros', {})))
    context = Contexto(0, portfolio, provider)
    seen: set[str] = set()
    notes = []
    nominal = net = discount = Decimal(0)
    for row in reader:
        line = reader.line_num
        try:
            n = parse_row(row, line)
        except FormatError as error:
            notes.append(dict(linha=line, cedente=row.get('NOME_CEDENTE'), sacado=row.get('NOME_SACADO'), numero_documento=row.get('NU_DOCUMENTO'), tipo=row.get('TIPO_RECEBIVEL'), valor_nominal=None, vencimento=None, dias=None, status='ERRO_DE_FORMATO', valor_liquido=None, desconto=None, motivos=[dict(codigo='ERRO_DE_FORMATO', campo=error.field, mensagem=f'Linha {line}, campo {error.field}: {error}', acao_sugerida='Corrija este campo no CSV e reenvie o arquivo.')], observacoes=[]))
            continue
        nominal += n.valor
        context.dias = (n.vencimento - reference).days
        reasons = []
        observations = []
        # Concentration is evaluated for all parseable rows to expose all failures;
        # only approved rows mutate the accumulated exposure.
        for rule in rules:
            result = rule.avaliar(n, context)
            if not result.ok:
                reasons.append(asdict(result))
            elif result.detalhes.get('carteira_vazia') or (len(n.doc_sacado) == 11 and rule.codigo in ('CNPJ_SACADO_VALIDO', 'SITUACAO_CADASTRAL_SACADO')):
                observations.append(result.mensagem)
        if integrity and (n.chave in seen or n.chave in portfolio.chaves):
            reasons.append(dict(codigo='DUPLICIDADE', mensagem='Esta nota já aparece no estoque ou em uma linha anterior deste arquivo.', acao_sugerida='Remova a repetição ou confira o número, a empresa que emitiu a nota e o tipo.'))
        seen.add(n.chave)
        liquid = reduction = None
        if not reasons:
            liquid, reduction = price(n, context.dias, policy['precificacao'])
            net += liquid
            discount += reduction
            context.aprovadas_total += n.valor
            context.sacados[n.raiz] = context.sacados.get(n.raiz, Decimal(0)) + n.valor
            context.cedentes[n.doc_cedente] = context.cedentes.get(n.doc_cedente, Decimal(0)) + n.valor
        notes.append(dict(linha=line, cedente=n.cedente, sacado=n.sacado, numero_documento=n.numero, tipo=n.tipo, valor_nominal=money(n.valor), vencimento=n.vencimento.isoformat(), dias=context.dias, status='RECUSADA' if reasons else 'APROVADA', valor_liquido=money(liquid) if liquid is not None else None, desconto=money(reduction) if reduction is not None else None, motivos=reasons, observacoes=observations))
    statuses = Counter(n['status'] for n in notes)
    failures = Counter(r['codigo'] for n in notes for r in n['motivos'])
    return dict(lote=dict(id=str(uuid4()), data_referencia=reference.isoformat(), total_notas=len(notes), aprovadas=statuses['APROVADA'], recusadas=statuses['RECUSADA'], erros=statuses['ERRO_DE_FORMATO'], valor_nominal_total=money(nominal), total_a_receber=money(net), desconto_total=money(discount)), notas=notes, resumo_recusas=[dict(codigo=k, quantidade=v, mensagem_resumo=f'{v} nota(s) com {k.lower().replace("_", " ")}.') for k, v in failures.items()], avisos=warnings)
