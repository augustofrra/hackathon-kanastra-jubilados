# Auditoria de duplicidade

Arquivo: `data/estoque_antecipe.csv`. SHA-256: `313c75f4147e1e851eaaefd15dc035aa895c961434da1a91024fd0764559c2f1`.

- Notas: 100.554; fundos: 18; chaves únicas: 90.897.
- Repetições após a primeira ocorrência no lote: 9.657.
- Mesmo número original: 9.657; números diferentes que convergem na normalização: 0.
- Coincidências com as 20 linhas do estoque anterior: 0.
- União das recusas por lote e estoque anterior: 9.657.
- Após seed oficial, reenviar este mesmo CSV encontra 100.554 notas no estoque. Isso é reapresentação, não uma contagem de repetições internas.

## Cinco pares reais

| Linhas CSV | NU_DOCUMENTO antes (primeira / repetida) | Depois (ambas) | DOC_CEDENTE (ambas) | Tipo (ambas) |
|---|---|---|---|---|
| 7371 / 7372 | `1-767495` / `1-767495` | `1767495` | `57543525000190` | Duplicata |
| 7385 / 7386 | `1-32996` / `1-32996` | `132996` | `05415825000190` | Duplicata de Serviço |
| 7397 / 7398 | `000577160` / `000577160` | `577160` | `73029619000100` | Duplicata |
| 7405 / 7406 | `861829` / `861829` | `861829` | `49364797000103` | Duplicata |
| 7443 / 7444 | `288146` / `288146` | `288146` | `07879093000115` | Duplicata de Serviço |

## Separação dos componentes

A chave inclui documento completo do cedente, tipo com caixa normalizada e número normalizado. O fundo não faz parte da chave, conforme o controle contra revenda entre fundos. Cada par acima tem o mesmo cedente e tipo. A auditoria compara a chave completa: coincidência apenas de número não gera duplicidade.

Foram preservadas 1.614 ocorrências com mesmo número/tipo e cedente diferente, e 0 com mesmo número/cedente e tipo diferente (comparação com a primeira ocorrência de cada grupo). Testes independentes cobrem ambos os casos, inclusive quando o estoque contém a outra nota.

Não se pode afirmar que toda colisão de pontuação representa o mesmo título econômico sem conferir o documento de origem. A normalização segue o requisito; os exemplos e linhas completas no JSON permitem revisão humana.

Reprodução: `.venv/bin/python scripts/audit_duplicates.py`. O JSON contém todas as linhas repetidas para confrontar o resultado exportado.

Confronto com o resultado exportado: 9657 recusas; mesmas linhas da auditoria: True.
