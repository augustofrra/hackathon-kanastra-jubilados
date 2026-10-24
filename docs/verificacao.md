# Verificação da entrega

Execução em 24/10/2026, Python 3.12 e Node 22.

- **27 testes pytest aprovados**: dígitos de CPF/CNPJ, preço por fora/por dentro, arredondamento por nota, igualdade nos limites, múltiplos motivos, provedor indisponível, mudanças de política sem reinício, códigos desconhecidos, exposição em ordem, carteira vazia, regra de cedente, duplicidade, erros por campo, seed idempotente/rollback/filtro por fundo e endpoints/upload.
- **Build TypeScript + Vite aprovado**. Dependências fixadas em `frontend/package-lock.json` e `backend/requirements.lock`.
- **Chromium / Playwright**: upload real do exemplo para FastAPI via proxy Vite, total de R$ 18.664,00, expansão dos motivos, filtro de erros e navegação na política aprovados. Nenhum erro JavaScript de página. Viewports 1440×1100 e 390×844; sem transbordamento horizontal da página. A tabela possui rolagem horizontal própria no celular.
- **Benchmark**: veja `benchmark.json`, estoque sintético de 100.000 registros em 18 fundos, lote de 5.000 notas, provedor simulado. Inclui agregados SQLite, motor e serialização JSON. Não é medição de rede externa nem validação do estoque oficial ausente.
- **Docker Compose não executado**: Docker não está instalado no ambiente. Execução local da API e frontend verificada no navegador.

Os testes HTTP e o navegador precisaram rodar fora do sandbox: o ambiente restrito bloqueia sockets e a comunicação entre threads do cliente de testes. O registro npm retornou 403; foi possível instalar e compilar usando versões disponíveis no cache local. Isso não modifica os passos usuais de instalação em outro ambiente com acesso ao registro.

Há um aviso de depreciação do TestClient/Starlette para seu transporte httpx; não houve falha de teste.

Capturas: [desktop](screenshots/desktop.png), [resultado](screenshots/resultados.png), [celular](screenshots/mobile.png).
