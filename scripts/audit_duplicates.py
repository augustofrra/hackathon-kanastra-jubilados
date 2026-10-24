"""Reproducible duplicate audit; no changes to stock or policy."""
import argparse
import hashlib
import json
import sys
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.storage import snapshot
from app.config import DB_PATH, load_policy
from app.domain import csv_reader, parse_row, normalized_number


def audit(path: Path, previous: Path | None = None) -> dict:
    content = path.read_bytes()
    reader = csv_reader(content)
    official_keys = snapshot(DB_PATH, load_policy()['fundo']['cnpj']).chaves
    official_matches = 0
    first = {}
    repeated = []
    examples = []
    transformations = set()
    cross_seller = cross_type = 0
    numbers = {}
    seller_numbers = {}
    raw_repeats = normalized_repeats = 0
    previous_keys = set()
    if previous:
        old = csv_reader(previous.read_bytes())
        previous_keys = {parse_row(row, old.line_num).chave for row in old}
    matches_previous = set()
    funds = Counter()
    for row in reader:
        n = parse_row(row, reader.line_num)
        funds[n.fundo] += 1
        official_matches += n.chave in official_keys
        number = normalized_number(n.numero)
        if n.chave in previous_keys:
            matches_previous.add(n.linha)
        # Cases that would collide if the key omitted cedente or tipo.
        other_seller = numbers.setdefault((number, n.tipo.casefold()), n.doc_cedente)
        other_type = seller_numbers.setdefault((number, n.doc_cedente), n.tipo.casefold())
        cross_seller += other_seller != n.doc_cedente
        cross_type += other_type != n.tipo.casefold()
        original = first.get(n.chave)
        if original is None:
            first[n.chave] = n
            continue
        repeated.append(n.linha)
        exact = original.numero == n.numero
        raw_repeats += exact
        normalized_repeats += not exact
        change = (original.numero[:3], n.numero[:3], exact)
        if len(examples) < 5 and change not in transformations:
            transformations.add(change)
            examples.append({'linhas': [original.linha, n.linha], 'numeros_originais': [original.numero, n.numero], 'numeros_normalizados': [normalized_number(original.numero), number], 'doc_cedente': [original.doc_cedente, n.doc_cedente], 'tipos': [original.tipo, n.tipo], 'chave': n.chave})
    return {'arquivo': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(content).hexdigest(), 'total_notas': sum(funds.values()), 'fundos': len(funds), 'chaves_unicas': len(first), 'repetidas_apos_primeira_no_lote': len(repeated), 'linhas_repetidas_no_lote': repeated, 'numero_original_identico': raw_repeats, 'numero_original_diferente': normalized_repeats, 'coincidencias_estoque_anterior': len(matches_previous), 'recusas_uniao_lote_e_estoque_anterior': len(set(repeated) | matches_previous), 'coincidencias_apos_seed_oficial': official_matches, 'colisoes_evitadas_cedente': cross_seller, 'colisoes_evitadas_tipo': cross_type, 'exemplos': examples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arquivo', type=Path, default=ROOT/'data/estoque_antecipe.csv')
    parser.add_argument('--estoque-anterior', type=Path, default=ROOT/'backend/tests/fixtures/estoque_anterior.csv')
    parser.add_argument('--resultado-anterior', type=Path)
    args = parser.parse_args()
    result = audit(args.arquivo, args.estoque_anterior)
    if args.resultado_anterior:
        exported = json.loads(args.resultado_anterior.read_text())
        lines = {n['linha'] for n in exported['notas'] if any(r['codigo'] == 'DUPLICIDADE' for r in n['motivos'])}
        result['confronto_exportacao'] = {'recusas': len(lines), 'mesmas_linhas': lines == set(result['linhas_repetidas_no_lote'])}
    (ROOT/'docs/auditoria_duplicidade.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    lines = ['# Auditoria de duplicidade', '', f"Arquivo: `{result['arquivo']}`. SHA-256: `{result['sha256']}`.", '', f"- Notas: {result['total_notas']:,}; fundos: {result['fundos']}; chaves únicas: {result['chaves_unicas']:,}.", f"- Repetições após a primeira ocorrência no lote: {result['repetidas_apos_primeira_no_lote']:,}.", f"- Mesmo número original: {result['numero_original_identico']:,}; números diferentes que convergem na normalização: {result['numero_original_diferente']:,}.", f"- Coincidências com as 20 linhas do estoque anterior: {result['coincidencias_estoque_anterior']:,}.", f"- União das recusas por lote e estoque anterior: {result['recusas_uniao_lote_e_estoque_anterior']:,}.", f"- Após seed oficial, reenviar este mesmo CSV encontra {result['coincidencias_apos_seed_oficial']:,} notas no estoque. Isso é reapresentação, não uma contagem de repetições internas.", '', '## Cinco pares reais', '', '| Linhas CSV | NU_DOCUMENTO antes (primeira / repetida) | Depois (ambas) | DOC_CEDENTE (ambas) | Tipo (ambas) |', '|---|---|---|---|---|']
    for example in result['exemplos']:
        lines.append(f"| {example['linhas'][0]} / {example['linhas'][1]} | `{example['numeros_originais'][0]}` / `{example['numeros_originais'][1]}` | `{example['numeros_normalizados'][0]}` | `{example['doc_cedente'][0]}` | {example['tipos'][0]} |")
    lines += ['', '## Separação dos componentes', '', 'A chave inclui documento completo do cedente, tipo com caixa normalizada e número normalizado. O fundo não faz parte da chave, conforme o controle contra revenda entre fundos. Cada par acima tem o mesmo cedente e tipo. A auditoria compara a chave completa: coincidência apenas de número não gera duplicidade.', '', f"Foram preservadas {result['colisoes_evitadas_cedente']:,} ocorrências com mesmo número/tipo e cedente diferente, e {result['colisoes_evitadas_tipo']:,} com mesmo número/cedente e tipo diferente (comparação com a primeira ocorrência de cada grupo). Testes independentes cobrem ambos os casos, inclusive quando o estoque contém a outra nota.", '', 'Não se pode afirmar que toda colisão de pontuação representa o mesmo título econômico sem conferir o documento de origem. A normalização segue o requisito; os exemplos e linhas completas no JSON permitem revisão humana.', '', 'Reprodução: `.venv/bin/python scripts/audit_duplicates.py`. O JSON contém todas as linhas repetidas para confrontar o resultado exportado.']
    if 'confronto_exportacao' in result:
        lines += ['', f"Confronto com o resultado exportado: {result['confronto_exportacao']['recusas']} recusas; mesmas linhas da auditoria: {result['confronto_exportacao']['mesmas_linhas']}."]
    report_text = re.sub(r'(?<=\d),(?=\d{3}\b)', '.', '\n'.join(lines))
    (ROOT/'docs/auditoria_duplicidade.md').write_text(report_text+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('linhas_repetidas_no_lote','exemplos')},ensure_ascii=False,indent=2))
