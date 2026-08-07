# CI — Testes Automatizados (GitHub Actions)

## Objetivo

Rodar a suíte `pytest` de `execution/tests/` automaticamente em todo Pull Request contra `main`, bloqueando merge se algum teste falhar.

## Decisões e por quê

### 1. `prisma generate` roda antes do `pytest` — confirmado necessário

`execution/tests/test_db_client_prisma_schema.py` importa o pacote `prisma` real (contornando o stub `MagicMock` do `conftest.py`) para detectar quando `schema.prisma` ganha um model novo (ex: `SearchResult`) mas ninguém rodou `prisma generate` — isso já aconteceu neste projeto e quebrava `db_client.save_search_results`/`get_search_results` em runtime. Sem `prisma generate` no CI, esse teste falharia sempre (client vazio), mascarando o que ele realmente verifica.

### 2. Nenhum serviço de banco de dados (Postgres) no workflow

Investigado antes de decidir — nenhum arquivo em `execution/tests/` chama `.connect()` real: todas as chamadas a `db_client.py` são mockadas via `unittest.mock.patch` (ver `test_worker_pipeline.py`, `MOCK_PATCHES`). O próprio `conftest.py` substitui o módulo `prisma` inteiro por `MagicMock` para a maioria dos testes.

`prisma generate` também não precisa de um banco alcançável — ele só lê `schema.prisma` e usa a variável `DATABASE_URL` para saber o provider (postgresql), sem abrir conexão. Testado localmente com uma URL falsa (`postgresql://user:pass@localhost:5432/dummy`) e funcionou normalmente.

**Decisão:** o workflow define `DATABASE_URL` como uma string dummy (env do job), sem subir `services: postgres`. Isso mantém o CI simples e rápido. Se no futuro um teste passar a exigir um Postgres real, adicionar a seção `services:` nesse momento.

### 3. Python 3.11 (não 3.12)

O `Dockerfile` de produção usa `python:3.11-slim` e o `pyrightconfig.json` fixa `pythonVersion: "3.11"`. O CI usa 3.11 para espelhar o ambiente real, mesmo que o `venv/` local do desenvolvedor esteja em 3.12.

### 4. Sem instalação de browser do Playwright

`conftest.py` faz stub de `playwright`/`playwright.sync_api` inteiro via `sys.modules` para todos os testes — nenhum teste executa Playwright de verdade (nem `test_scrapers.py`, que mocka a cadeia `sync_playwright()` diretamente). Rodar `playwright install chromium` no CI seria desperdício de tempo (é o passo mais lento do `Dockerfile`) sem nenhum benefício para os testes atuais.

### 5. Cache de dependências não interfere no drift do schema

`actions/setup-python` com `cache: pip` cacheia apenas os wheels baixados pelo `pip install`, não o resultado de `prisma generate`. Como cada job roda em um runner novo, `prisma generate` sempre gera o client a partir do `schema.prisma` do commit do PR — não há risco de reusar um client cacheado de uma execução anterior.

### 6. Gatilho: só `pull_request` para `main`

Only o que foi pedido — sem lint, build ou deploy. `push` direto para `main` normalmente já passou por um PR revisado, então não foi adicionado (mantém o escopo mínimo pedido).

### 7. `requirements-dev.txt` separado — correção pós primeira execução real

Primeira execução no GitHub Actions falhou com `pytest: command not found` (exit 127). Causa: `pytest` nunca esteve listado em `requirements.txt` — só existia instalado manualmente no `venv/` local do desenvolvedor, fora de qualquer arquivo de dependências rastreado. `pip install -r requirements.txt` no runner, portanto, nunca instalava o `pytest`.

**Correção:** `requirements-dev.txt` novo na raiz, com `pytest==9.1.1` (versão já em uso localmente). Separado de `requirements.txt` de propósito — este último também alimenta o `Dockerfile` da imagem de produção (`RUN pip install -r requirements.txt`), e dependência de teste não deveria inflar essa imagem. O workflow agora instala os dois arquivos e chama `python -m pytest` (em vez de `pytest` puro) para usar explicitamente o interpretador configurado pelo `actions/setup-python`, evitando problemas de `PATH`.

## Workflow

Arquivo: `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  pull_request:
    branches: [main]

jobs:
  pytest:
    runs-on: ubuntu-latest
    env:
      DATABASE_URL: "postgresql://ci:ci@localhost:5432/ci_dummy"
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - run: pip install -r requirements.txt -r requirements-dev.txt

      - run: prisma generate

      - run: python -m pytest execution/tests -v
```

## Validação local

Passos simulados manualmente antes de finalizar (sem Docker, replicando o que o CI faz):

```bash
DATABASE_URL="postgresql://ci:ci@localhost:5432/ci_dummy" prisma generate
python -m pytest execution/tests -v
```

Resultado: `prisma generate` completou sem erro (não exige banco alcançável) e os 76 testes de `execution/tests/` passaram.
