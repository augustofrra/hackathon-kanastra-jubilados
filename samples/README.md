# Lote de demonstração de cenários

`lote_demo.csv` contém exatamente 20 notas fictícias, separadas dos dados oficiais. Baixe também pela tela. Referência: **22/10/2026**; estoque oficial carregado com `make seed`; provedor cadastral padrão simulado.

| Linha CSV | Cenário | Resultado / regras |
|---|---|---|
| 2 | 20261001 | APROVADA —  |
| 3 | 20261002 | RECUSADA — CNPJ_SACADO_VALIDO, SITUACAO_CADASTRAL_SACADO |
| 4 | 20261003 | RECUSADA — TIPO_RECEBIVEL |
| 5 | 20261004 | RECUSADA — VALOR_MINIMO |
| 6 | 20261005 | RECUSADA — NAO_VENCIDA |
| 7 | 20261006 | RECUSADA — PRAZO_MAXIMO |
| 8 | 20261007 | RECUSADA — CONCENTRACAO_MAXIMA_SACADO |
| 9 | NF-020261001 | RECUSADA — DUPLICIDADE |
| 10 | 20261009 | ERRO_DE_FORMATO — ERRO_DE_FORMATO |
| 11 | 20261010 | APROVADA —  |
| 12 | 20261011 | APROVADA —  |
| 13 | 20261001 | APROVADA —  |
| 14 | 20261001 | APROVADA —  |
| 15 | 20261014 | APROVADA —  |
| 16 | 20261015 | APROVADA —  |
| 17 | 20261016 | APROVADA —  |
| 18 | 20261017 | APROVADA —  |
| 19 | 20261018 | APROVADA —  |
| 20 | 20261019 | APROVADA —  |
| 21 | 20261020 | APROVADA —  |

Resultado padrão: 12 aprovadas, 7 recusadas, 1 erro de formato.

A linha 3 tem CNPJ com dígito verificador inválido e recusa também na regra cadastral, pois não é possível consultar esse documento. Não representa consulta real nem baixa fiscal simulada. A linha 9 repete a primeira nota com prefixo NF e zeros; linha 10 tem valor malformado. Linhas 13 e 14 repetem o número da primeira nota, mas mudam, respectivamente, cedente e tipo; devem ser aprovadas, sem DUPLICIDADE.

Regras inativas: a linha 11 (vencimento em 1 dia) reprova ao ativar PRAZO_MINIMO; a linha 12 (R$ 4.500.000,00) reprova ao ativar CONCENTRACAO_MAXIMA_CEDENTE. Os testes ligam ambas e confirmam os motivos. Aprovações e valores dependem da política vigente e do estoque; não há resultados fixados na interface.
