# Decisões de negócio e implementação

## Origem dos dados
O diretório recebido estava vazio. Os arquivos em `data/` são **sintéticos e demonstrativos**, com 20 posições de estoque. Os valores da política reproduzem o enunciado; nomes e documentos não representam uma carteira real. Substitua `validadores_antecipe.json` e `estoque_antecipe.csv` pelos arquivos oficiais, retire `demonstrativo` do JSON e execute `make seed`. O gerador de exemplos não sobrescreve arquivos existentes.

## Referência e preço
A data explícita da requisição tem prioridade sobre `DATA_REFERENCIA`; sem ambos, usa-se a data do processo, configurado com `TZ=America/Sao_Paulo` no Docker. Para reproduzir os exemplos, escolha **22/10/2026**. Dias são corridos: vencimento menos referência. A aquisição é validada como data, mas não altera o prazo.

Preço comercial por fora: `VN × (1 − taxa_mensal_percentual/100 × dias/base_dias)`. O valor líquido é arredondado por nota com `Decimal` e `ROUND_HALF_UP`, duas casas; desconto = nominal menos líquido arredondado; totais somam as parcelas já arredondadas. Dinheiro na API é string decimal. O frontend apenas formata essas strings, sem calcular preços. SQLite armazena centavos inteiros, nunca REAL. O JSON é lido com `parse_float=Decimal`.

`STRATEGIES` permite trocar a fórmula por `DESCONTO_POR_DENTRO`: `VN / (1 + taxa × dias/base)`. Política que gera preço negativo causa resposta 422, sem publicar um resultado financeiro parcial. Não há piso silencioso ou preço calculado para nota recusada.

## Elegibilidade
Só regras com `ativo=true` são executadas. A política é relida a cada requisição; o registro vincula código a classe. Código desconhecido gera aviso em log e na resposta, sendo ignorado. Parâmetros inválidos tornam a política indisponível (503), em vez de usar limites implícitos. Os nomes canônicos de parâmetros estão no JSON entregue.

Limites inclusivos: nominal ≥ mínimo; dias ≤ máximo; dias ≥ mínimo; vencimento ≥ referência. Prazo mínimo e concentração por cedente estão implementados, inicialmente inativos. As mensagens usam parâmetros vigentes.

Documento malformado (tamanho/caracteres) é erro de formato. Dígitos verificadores incorretos do sacado são recusa pela regra documental quando ativa. CPF de 11 dígitos tem validação própria e observação de que CNPJ não se aplica. Consulta cadastral de CNPJ também não se aplica a CPF. Documentos do fundo e cedente passam por validação sintática; a regra de dígitos verificadores solicitada é específica do sacado.

## Cadastro
`ProvedorSituacaoCadastral` é a interface. O padrão `ProvedorSimulado` retorna ATIVA e permite exceções determinísticas no mapa `situacoes_simuladas` do JSON (BAIXADA e null para falha). A interface identifica claramente a consulta simulada: não equivale à verificação fiscal real.

Para consulta externa, use `PROVEDOR_CADASTRAL=brasilapi`. O adaptador faz GET em `/api/cnpj/v1/{cnpj}` da BrasilAPI, lê `descricao_situacao_cadastral`, tem timeout de 2 segundos, uma repetição, cache de sucesso de 1 hora e cache de falha de 30 segundos. Há também cache por lote. Falhas recusam a nota com o motivo “Não foi possível verificar a situação cadastral do sacado (seu cliente)”. Para outro serviço, implemente `consultar(documento) -> str | None` e selecione a instância em `main.execute`. Cache é local ao processo. O alvo de 3 segundos vale para provedor simulado/cache aquecido, não para milhares de consultas de rede inéditas.

## Concentração
Estoque agregado somente para `DOC_FUNDO` igual ao CNPJ normalizado da política. Sacados CNPJ agrupados pelos 8 primeiros dígitos; CPF pelo documento completo, para não agrupar pessoas diferentes por prefixo. Cedentes pelo documento completo.

Conforme a fórmula solicitada, **denominador = estoque atual do fundo + nominal das notas anteriormente aprovadas**; a candidata ainda não entra no denominador. **Numerador = estoque do grupo + aprovadas anteriores do grupo + candidata**. Não substituímos esta fórmula por uma concentração pós-compra convencional. Lote processado na ordem original. Somente aprovadas aumentam os acumuladores. As regras de concentração também são avaliadas para notas com outras falhas, para mostrar todos os motivos, sem consumir limite.

Carteira vazia e nenhuma aprovação anterior: dispensa-se a concentração para a primeira nota elegível, com observação explícita. A partir dela, aplica-se a fórmula normal. Isso evita divisão por zero; pode tornar restritiva a formação inicial de uma carteira pequena. Não inventamos um patrimônio mínimo ou limite absoluto que não consta da política.

## Duplicidade e erros
Controle fixo `DUPLICIDADE`, desligável por `INTEGRIDADE_ATIVA=false`. Chave = cedente normalizado + tipo sem distinção de caixa + número normalizado. Número: trim, caixa alta, remoção de pontuação, prefixo NF antes de números e zeros à esquerda; `25`, `025`, `NF-25` colidem. Outros prefixos alfanuméricos são preservados. Estoque inteiro (inclusive outros fundos) é verificado para evitar reapresentação do mesmo título. Uma linha anterior parseável reserva a chave no lote mesmo se recusada; controle de repetição é independente da exposição aprovada.

Valor positivo com até duas casas, vírgula decimal e pontos opcionais de milhar; datas estritamente dd/mm/aaaa; campos obrigatórios e quantidade de colunas são verificados. Linha inválida produz `ERRO_DE_FORMATO` com linha física e campo, e as demais continuam. Primeiro campo de formato inválido é informado, pois a nota não pode ser formada para executar regras financeiras. Todas as falhas de regras de uma nota válida são retornadas. Cabeçalho ou codificação ilegíveis impedem o arquivo inteiro (422). Valor nominal total inclui notas válidas sintaticamente, aprovadas ou recusadas; erros não possuem valor confiável e são excluídos.

## Arquitetura e limites
A tela chama a mesma API usada por integrações; nenhuma regra financeira é replicada em TypeScript. Snapshot SQLite por lote: total, agregado sacado, agregado cedente, conjunto de chaves. Não há consulta de estoque por nota. Índices de fundo, cedente, raiz e chave, com compostos por fundo. Seed usa transação, `executemany` em blocos de 2.000 e substituição atômica; erro reverte a carga anterior. Reexecução não duplica estoque.

Simulação não compra notas, não altera estoque e não persiste uploads ou resultados. Resultados são mantidos na tela e podem ser exportados em JSON. Sem autenticação, contratação, liquidação ou consulta externa obrigatória: escopo de hackathon local. O limite padrão de upload é 50 MiB; API verifica o corpo multipart antes de parsing e o tamanho do arquivo. Nginx tem teto de 51 MiB, a ajustar se o limite da API aumentar. A paginação visual mostra 50 linhas por vez para lotes grandes.
