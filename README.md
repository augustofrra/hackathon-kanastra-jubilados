# Portal Antecipe

Portal responsivo React + TypeScript + Vite + Tailwind e API FastAPI/Pydantic v2 para validar CSVs de recebíveis, explicar recusas e precificar aprovadas com Decimal. SQLite indexado; uma implementação de regras atende tela e API.

**Os dados oficiais não estavam no diretório recebido.** Política e estoque incluídos são demonstrativos. O anexo terminava na especificação visual “foco visível”; a interface completa o fluxo descrito com upload, política, resumo, filtros, motivos e exportação JSON.

## Rodar com Docker

```bash
cp .env.example .env
# Opcional: DATA_REFERENCIA=2026-10-22 no .env para reproduzir o exemplo.
docker compose up --build
```

Abra http://localhost:8080. API e documentação: http://localhost:8000/docs. O serviço seed carrega o estoque antes da API. Regras JSON são lidas novamente em cada chamada. A simulação não altera o estoque.

## Rodar localmente (Python 3.12 e Node 22)

```bash
make setup
make seed
# Terminal 1
make api
# Terminal 2
make web
```

Abra http://localhost:5173. Para carregar `.env` nos comandos locais: `set -a; source .env; set +a` antes de iniciar. Sem `.env`, usa a data atual. No formulário, escolha **22/10/2026** e envie `data/notas_exemplo.csv`: o resultado esperado é **3 aprovadas, 4 recusadas, 1 erro**, líquido **R$ 18.664,00**, desconto **R$ 636,00**. O botão de download da tela fornece esse mesmo exemplo.

## Dados reais

1. Substitua `data/validadores_antecipe.json` e `data/estoque_antecipe.csv` pelos arquivos oficiais, mantendo os parâmetros canônicos documentados no exemplo.
2. Remova `demonstrativo` e `situacoes_simuladas` do JSON se não se aplicarem.
3. Execute `make seed` (ou `docker compose run --rm seed`). O comando substitui o estoque de forma transacional e idempotente.
4. Ajuste referência e provedor conforme o cenário. O provedor padrão é simulado e não consulta Receita Federal.

CSV UTF-8 com cabeçalho, `;`, decimal com vírgula, datas dd/mm/aaaa. Colunas:

```text
NOME_FUNDO;DOC_FUNDO;NOME_CEDENTE;DOC_CEDENTE;NOME_SACADO;DOC_SACADO;NU_DOCUMENTO;TIPO_RECEBIVEL;VALOR_NOMINAL;DATA_VENCIMENTO_ORIGINAL;DATA_AQUISICAO
```

## API

```bash
curl -F 'arquivo=@data/notas_exemplo.csv;type=text/csv' \
     -F 'data_referencia=2026-10-22' \
     http://localhost:8000/api/v1/validacoes
```

- `POST /api/v1/validacoes`: multipart `arquivo`, `data_referencia` opcional (AAAA-MM-DD); resultado por nota, totais, resumo de recusas e avisos.
- `GET /api/v1/regras`: política vigente, data padrão, integridade e identificação do provedor.
- `GET /api/v1/saude`: saúde e provedor selecionado.
- `/docs`: OpenAPI interativo.

Dinheiro retornado como string decimal. Erros globais usam `application/problem+json`, com `type`, `title`, `status`, `detail` e `instance`. Erros por linha ficam no lote, sem abortar as demais.

## Verificação

```bash
make test
make build
npm test --prefix frontend
make benchmark
```

Benchmark gera temporariamente 100.000 posições distribuídas em 18 fundos e valida 5.000 notas, incluindo snapshot SQLite e serialização JSON. Relatório em `docs/benchmark.json`. Dados são sintéticos e o provedor é simulado.

## Organização

- `backend/app/domain.py`: parsing, documentos, Decimal e estratégias de preço.
- `backend/app/rules.py`: interface, classes de regras e registro.
- `backend/app/engine.py`: ordem do lote, motivos, duplicidade e totais.
- `backend/app/providers.py`: cadastro simulado e adaptador BrasilAPI.
- `backend/app/storage.py`: SQLite, agregados e seed.
- `frontend/src/`: interface responsiva, acessível por teclado, com foco visível.
- [Decisões e casos de borda](docs/decisoes.md).
- [Testes, verificação visual e limitações](docs/verificacao.md).

Adicionar uma regra: implementar `avaliar(nota, contexto) -> ResultadoRegra`, registrar a classe em `REGISTRO` e configurá-la no JSON. A política não contém valores financeiros fixados no código do motor.

O limite padrão de envio é **50 MB**, configurável por `MAX_UPLOAD_MB`. A tela consulta esse limite na API e verifica o tamanho antes do envio. Se um `.env` anterior definir `MAX_UPLOAD_MB=10`, atualize para `50`, recarregue as variáveis e reinicie a API. No Docker, o Nginx aceita até 51 MB incluindo o multipart.
