# Plano: Melhores Valores como executável desktop (branch `exe`)

> Base: [guia para transformar em executável](Melhores%20Valores%20guia%20para%20transformar%20em%20execut%C3%A1vel.md) + leitura do código atual.
> Objetivo: o usuário baixa um `.exe` (e builds para macOS/Linux), abre, e tem o app completo rodando localmente, **sem Docker, PostgreSQL, Redis ou Celery**, com as mesmas funcionalidades de hoje.

> **Escopo (confirmado):** a versão web/servidor continua normalmente na `main` e não é alterada. A `exe` é uma versão à parte para testar o executável, que vai para **poucas pessoas** testarem. Cada testador começa **zerado**: banco vazio criado na primeira abertura, sem nenhum dado nem chave do desenvolvedor. Os dados da versão web **nunca são alterados**; para testes, eles só podem ser **copiados** (ver Fase 6).

---

## 1. Princípio que guia todas as fases

**Trocar só a infraestrutura, nunca a regra de negócio.**

Cada módulo de infraestrutura será reescrito **mantendo a mesma API pública** (nomes de função, parâmetros e formato de retorno). Assim:

- `web_server.py`, os adapters, os scrapers e os orquestradores continuam iguais (ou quase).
- O frontend (`apps/web`) **não muda nenhuma linha**.
- Os testes existentes, que mockam essas funções públicas, continuam válidos.
- Correções de adapters/scrapers feitas na `main` podem ser trazidas para a `exe` com `git merge main` sem conflito, porque esses arquivos não são tocados aqui.

| Camada | Muda? | Arquivos |
| --- | --- | --- |
| Regra de negócio (adapters, scrapers, orquestradores, detecção de loja) | **Não** | `adapters/`, `scrapers/base_scraper.py`, `search_scrapers/`, `scraping_orchestrator.py`, `search_orchestrator.py`, `store_detection.py` |
| Rotas HTTP | **Não** (só passam a ser montadas em `/api`) | `web_server.py` |
| Frontend | **Não** | `apps/web/`, `packages/` |
| Infraestrutura | **Sim**, mesma interface | `db_client.py`, `cache_manager.py`, `search_status.py`, `worker_tasks.py` |
| Novo | — | `settings.py`, `models.py`, `db_schema.py`, `task_runner.py`, `desktop_app.py`, `main.py`, `packaging/` |

---

## 2. O que o guia não viu (ele foi feito só pelo README)

Pontos encontrados no código que mudam ou detalham o plano do guia:

1. **As rotas do SPA colidem com as da API.** O React Router tem as páginas `/products` e `/search`, e a API também tem `GET /products` e `POST /search`. Se o FastAPI servir tudo na raiz, um F5 em `/products` devolve JSON em vez da página.
   → **Solução:** montar a API em `/api` no app desktop. O `apps/web/src/services/api.ts` já usa `baseURL: '/api'` por padrão (e o proxy do Vite já reescreve `/api`), então **o frontend não precisa mudar**, nem o `VITE_API_URL`.
2. **Os endpoints reais são outros:** `/products`, `/products/promotions`, `/products/group-stats`, `/product/{id}/history`, `/product/{id}/refresh`, `/product/{id}/name`, `/product/{id}/status`, `DELETE /product/{id}`, `/monitor/add`, `/search`, `/search/{id}`. Todos são preservados.
3. **O resto do código usa os objetos do Prisma por atributo:** `p.history[0]`, `p.imageUrl`, `latest.scrapedAt`, `r.model_dump(mode="json")`. Os modelos do Prisma Python são Pydantic.
   → **Solução:** criar `execution/models.py` com modelos Pydantic `Product`, `PriceHistory` e `SearchResult` com **os mesmos nomes de campo** (camelCase em `Product`/`PriceHistory`, snake_case em `SearchResult`, como no `schema.prisma`). O `db_client.py` novo devolve esses objetos.
4. **Há SQL específico do Postgres:** `get_price_stats` e `get_group_price_stats` usam `percentile_cont(...) WITHIN GROUP`, que o SQLite não tem.
   → Calcular mínimo e média em SQL e a mediana em Python (`statistics.median`) sobre a coluna `price`. O volume por produto é pequeno.
5. **Ordenação de `NULL` é diferente:** o Postgres coloca `NULL` por último em `ORDER BY price ASC`, o SQLite coloca primeiro. `get_search_results` promete "sem preço ao final".
   → Usar `ORDER BY price IS NULL, price ASC`.
6. **Datas:** o Prisma devolve `datetime` com fuso (UTC). `add_price_history` depende disso (`_is_same_brt_day` usa `astimezone`). Gravar em ISO 8601 UTC e converter de volta para `datetime` *aware* na leitura.
7. **O Redis tem dois usos, não um:** cache de preço (`cache_manager.py`) **e** avisos de loja bloqueada por busca (`search_status.py`, TTL 30 min). Os dois migram juntos.
8. **O Firecrawl já é opcional:** `firecrawl_api.scrape_product_data` devolve `{}` quando não há `FIRECRAWL_API_KEY`. Só falta expor onde o usuário coloca a própria chave.
9. **O Celery é usado com `.delay()` e `task.id`:** `web_server.py` faz `process_price_check.delay(...)` e `task_search_products.delay(...)`, e a busca usa `self.request.id` como `search_id`. Um *shim* com a mesma interface evita mexer no `web_server.py`.
10. **O agendamento só roda com o app aberto.** Rodar de 6 em 6 horas contando do momento em que o app abre não basta para quem abre o app por 20 minutos por dia. É preciso uma **checagem de recuperação na abertura**: se a última rodada foi há mais de 6h, roda já.
11. **No Windows 10/11 o Edge (Chromium) já vem instalado.** O Playwright pode usá-lo com `channel="msedge"`, o que evita embutir ou baixar ~150 MB de Chromium na maioria das máquinas Windows.
12. **Os testes atuais estão amarrados ao Prisma/Redis:** `conftest.py` cria stubs de `prisma`, `celery` e `redis`. `test_db_client_prisma_schema.py` importa o Prisma real, e `test_search_status.py` faz patch de `redis_client`. Esses três precisam ser ajustados. Em troca, o `db_client` passa a ter **testes reais** (SQLite em `tmp_path`, sem Docker).

---

## 3. Arquitetura alvo

```
MelhoresValores.exe  (1 processo)
│
├── main.py ─────────── garante instância única, escolhe porta livre, sobe uvicorn em 127.0.0.1 e abre o navegador
│
└── desktop_app.py (FastAPI raiz)
    ├── /api/*  ───────► web_server.app (rotas atuais, sem mudança)
    │                      │
    │                      ├── task_runner (ThreadPoolExecutor, 2 workers)  ← substitui Celery worker
    │                      │     └── worker_tasks.run_price_pipeline / run_product_search
    │                      ├── cache_manager (dict em memória + TTL)        ← substitui Redis
    │                      └── db_client (sqlite3, WAL)                     ← substitui Prisma/Postgres
    │
    ├── /*      ───────► arquivos do `pnpm build` (SPA, com fallback para index.html)
    │
    └── lifespan: APScheduler (a cada 6h + recuperação na abertura)        ← substitui Celery Beat

Pasta de dados do usuário (platformdirs):
  Windows: %LOCALAPPDATA%\MelhoresValores\
    ├── melhores_valores.db   (SQLite)
    ├── config.env            (FIRECRAWL_API_KEY opcional, porta, etc.)
    ├── logs\app.log
    └── browsers\             (Chromium baixado sob demanda, se preciso)
```

---

## 4. Fases

Cada fase termina com um critério verificável. **Não começar a próxima sem passar no critério da anterior.** Até a Fase 5 tudo roda com `python main.py`; só a Fase 7 empacota.

### Fase 0: Preparação da branch ✅

**Objetivo:** ponto de partida limpo e com testes passando.

- [x] Corrigir o `pnpm-workspace.yaml`: o pnpm adicionou `allowBuilds: esbuild: set this to true or false` (um placeholder que não é um valor válido). Trocado por `esbuild: true` (o Vite precisa do binário do esbuild).
- [x] Versionar o guia e este plano em `docs/`.
- [x] Incluir a branch `exe` nos gatilhos do `.github/workflows/tests.yml`.
- [x] Linha de base registrada: 104 testes Python e 27 do frontend passando.

**Pronto quando:** CI verde na branch `exe`.

---

### Fase 1: Configuração e pasta de dados (parcial)

**Objetivo:** um lugar só para caminhos e configuração, funcionando em dev e no executável.

Novo `execution/settings.py`:
- [x] `DATA_DIR`: `platformdirs.user_data_dir("MelhoresValores", appauthor=False)`, sobrescrevível pela env `MV_DATA_DIR` (útil em dev e nos testes).
- [x] `DB_PATH` (sobrescrevível por `MV_DB_PATH`). A pasta é criada pelo `db_client` na primeira conexão, para o import não criar pastas.
- [x] Carrega `DATA_DIR/config.env` (prioridade) e o `.env` do repo com `python-dotenv`.
- [ ] `LOG_DIR` e `BROWSERS_DIR` (entram nas Fases 5 e 6).
- [ ] `is_frozen()`: `getattr(sys, "frozen", False)`, e `resource_path()` para achar o `web_dist` dentro do pacote do PyInstaller (`sys._MEIPASS`) (entra na Fase 5).

**Pronto quando:** `python -c "from execution.settings import DATA_DIR; print(DATA_DIR)"` mostra a pasta e ela é criada.

---

### Fase 2: Banco de dados, de Prisma/Postgres para SQLite ✅

> **Feito.** O que mudou em relação ao planejado:
> - O schema ficou em `execution/db_schema.py` (lista `MIGRATIONS` em Python), não em `schema.sql`, para não precisar de arquivo de dados extra no PyInstaller.
> - O lock de escrita também envolve a abertura da conexão (`PRAGMA journal_mode = WAL` + migrações). O teste de concorrência mostrou `database is locked` quando duas threads abriam a primeira conexão ao mesmo tempo.
> - Média, menor e mediana são calculadas em Python sobre a lista de preços.
> - O `docker-compose.yml` perdeu o serviço `db` e passou a usar `MV_DATA_DIR=/app/.data`. **Não use o modo Docker nesta branch:** api e worker seriam processos diferentes escrevendo no mesmo SQLite por um bind mount, o que não é confiável. Ele sai de vez na Fase 5.
> - Validação: as rotas reais (`/search/{id}`, `/monitor/add`, `/products`, `/product/{id}/refresh` com scraping real, `/history`, `/group-stats`, `/promotions`, PATCH de nome/status, DELETE) foram exercitadas contra um SQLite real com `TestClient`. Só `.delay()` e o `set` do cache Redis foram substituídos, já que Celery e Redis saem nas Fases 3 e 4.
> - O script `scripts/pg_to_sqlite.py` (opcional) ainda não foi feito.

**Objetivo:** reescrever `db_client.py` com **as mesmas funções públicas**, mesmas assinaturas e mesmos retornos: `connect_db`, `is_garbage_name`, `get_or_create_product`, `get_product_by_id`, `update_product_name`, `update_product_status`, `add_price_history`, `get_price_stats`, `get_group_price_stats`, `get_latest_price_entry`, `get_price_history_chart`, `get_price_history_page`, `get_all_products`, `get_products_with_history`, `delete_product`, `save_search_results`, `get_last_valid_price_for_url`, `get_search_results`.

**Decisão:** `sqlite3` da biblioteca padrão em vez de SQLAlchemy. São 3 tabelas e o `db_client` já é o único ponto de acesso. Assim não entra mais nenhuma dependência e o executável fica menor.

Tarefas:
- [x] `execution/models.py`: modelos Pydantic espelhando o `schema.prisma`.
  - `PriceHistory(id, price, inStock, scrapedAt, productId)`
  - `Product(id, url, name, imageUrl, store, status, createdAt, updatedAt, history: list[PriceHistory] | None = None)`
  - `SearchResult(id, search_id, query, store, title, price, currency, image_url, product_url, rating, review_count, found_at)`
- [x] `execution/db_schema.py`: as 3 tabelas + índices (`PriceHistory(productId, scrapedAt)`, `SearchResult(search_id)`, `SearchResult(query, store)`), `UNIQUE(url)` e `FOREIGN KEY ... ON DELETE CASCADE`.
- [x] Migrações por `PRAGMA user_version`: `connect_db()` aplica os itens pendentes de `MIGRATIONS`, cada um numa transação. Isso substitui o `prisma migrate`.
- [x] Conexão: uma por thread (`threading.local`), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `timeout=5`, e um `threading.RLock` nas escritas (a API e 2 threads de worker escrevem ao mesmo tempo).
- [x] Reescrever cada função com a mesma lógica de hoje:
  - `get_or_create_product`: mesma regra de atualizar nome lixo (`_is_garbage_name`), mantendo o alias público `is_garbage_name`.
  - `add_price_history`: mesma deduplicação por dia em `America/Sao_Paulo`.
  - `get_price_stats` / `get_group_price_stats`: `MIN`/`AVG` em SQL, mediana com `statistics.median` (ver item 4 da seção 2).
  - `get_all_products`: produtos + **só o último** histórico de cada um (window function `ROW_NUMBER() OVER (PARTITION BY productId ORDER BY scrapedAt DESC)`). `get_products_with_history` traz o histórico completo.
  - `get_search_results`: `ORDER BY price IS NULL, price ASC`.
  - `updatedAt`: atualizar manualmente em todo `UPDATE` (o Prisma fazia isso com `@updatedAt`).
  - IDs: `str(uuid.uuid4())`, como o `@default(uuid())`.
- [x] Remover o hack de `sys.stdout.fileno` (existia só por causa do Prisma dentro do Celery).
- [x] Testes: `test_db_client_prisma_schema.py` trocado por `test_db_client_sqlite.py` (34 testes) com banco real em `tmp_path`, cobrindo deduplicação, estatísticas/mediana, ordem com `NULL`, cascata do delete, datas com fuso, migração e escrita concorrente entre threads. O `conftest.py` aponta `MV_DATA_DIR` para uma pasta temporária, para nenhum teste tocar a pasta real.
- [x] `prisma` removido do `requirements.txt` (entrou `platformdirs`), do `conftest.py`, do `Dockerfile` e do CI. O `schema.prisma` e `migrations/` saíram da branch `exe` (continuam existindo na `main`).
- [ ] Opcional: `scripts/pg_to_sqlite.py` para quem já tem dados no Postgres do Docker levar o histórico para o app desktop.

**Pronto quando:** todos os testes passam e `uvicorn execution.web_server:app` (ainda com Celery/Redis do Docker) funciona usando SQLite. Isso isola a troca do banco das outras.

---

### Fase 3: Cache e status de busca, de Redis para memória ✅

**Objetivo:** tirar o Redis sem mudar quem chama.

- [x] `cache_manager.py`: classe `TTLCache` própria, pequena e thread-safe (dict + `time.monotonic()` + `Lock`, relógio injetável para testes), sem dependência nova. `get_cached_price(url)` e `set_cached_price(url, price, name, store, ttl=7200)` mantidos, com a mesma chave SHA256 e o valor guardado como JSON (quem lê recebe uma cópia).
- [x] Instância `memory_cache` com `get(key)` e `setex(key, ttl, value)` no lugar de `redis_client`; o `search_status.py` mudou só o import.
- [x] `search_status.py` usa esse cache (TTL de 30 min mantido).
- [x] Chaves expiradas são descartadas na leitura e, quando o cache passa de 1024 chaves, a cada escrita, para a memória não crescer sem limite com o app aberto por dias.
- [x] Testes: `test_cache_manager.py` (13 testes: TTL, sobrescrita, limpeza, concorrência, cache de preço) e `test_search_status.py` ajustado + teste de ida e volta com expiração. Total: 149 testes passando.
- [ ] Remover `redis` do `requirements.txt`: **adiado para a Fase 4**. O Celery ainda usa o Redis como broker e precisa do pacote `redis`. Nenhum módulo do projeto importa mais o `redis` diretamente.

Perder o cache ao fechar o app é aceitável: é só otimização (diretiva `05_caching_rules.md`).

> **(Resolvido na Fase 4, quando tudo passou a rodar num processo só.)** Até a Fase 4 entrar, o cache vivia dentro de cada processo. Enquanto API (uvicorn) e worker (Celery) forem processos separados, (1) os avisos de loja bloqueada gravados pela busca no worker **não chegam** ao `GET /search/{id}` da API, e (2) o cache de preço do worker não é visto pelo `/refresh` da API (que já ignora o cache, então isso não muda nada). Os dois voltam a funcionar quando tudo rodar num processo só (Fase 4).
>
> Validação: com o scraper simulado (o Mercado Livre devolveu `login_wall` nessa rodada), `run_price_pipeline` fez scraping na 1ª chamada, respondeu `source=cache` na 2ª e voltou a fazer scraping com `skip_cache=True`; os avisos de busca fizeram ida e volta.

**Pronto quando:** testes passando e nenhuma importação de `redis` no código do projeto. ✅

---

### Fase 4: Fila e agendamento, de Celery para threads + APScheduler ✅

**Objetivo:** tirar o Celery mantendo `.delay()` e `task.id` no `web_server.py`.

- [x] Novo `execution/task_runner.py`:
  - `ThreadPoolExecutor(max_workers=2)` (igual ao `--concurrency=2` atual), criado sob demanda e recriado se for encerrado.
  - Decorador `@task` / `@task(bind=True)`: `.delay(*args, **kwargs)` gera `uuid4`, submete ao pool e devolve `TaskHandle(id, future)`. Com `bind=True`, injeta um `self` com `self.request.id == handle.id`, então `task_search_products` continua usando o mesmo ID como `search_id`. Chamar a função direto executa na thread atual, como no Celery.
  - Exceções dentro da task vão para o log com o id da tarefa (o pool engoliria em silêncio).
  - `shutdown()` chamado ao fechar o app (descarta o que estava na fila).
- [x] `worker_tasks.py`: `Celery(...)`, `@app.task` e `beat_schedule` substituídos pelo `@task` novo. `run_price_pipeline`, `process_price_check`, `schedule_all_products` e `task_search_products` continuam com o mesmo corpo.
- [x] Agendador (`execution/scheduler.py`):
  - `BackgroundScheduler` do APScheduler (UTC), `run_full_check` a cada 6h, `max_instances=1`, `coalesce=True`, `misfire_grace_time=None` (se o PC dormir, roda ao acordar).
  - **Recuperação na abertura:** `last_full_check` fica numa tabela `AppMeta` do SQLite (migração v2). Ao abrir, a próxima rodada vai para última + 6h; se esse horário já passou (ou nunca rodou), para daqui a 1 minuto. Isso mantém o ritmo de 6h entre aberturas, em vez de recomeçar a contagem a cada abertura.
  - Diferença em relação ao Celery Beat: o Beat rodava em horários fixos (`crontab(minute=0, hour="*/6")`); agora o intervalo conta a partir da última rodada.
- [x] `web_server.py` ganhou um `lifespan` (liga o agendador; no fechamento, desliga agendador e pool). Ele é exportado para o app desktop da Fase 5 reaproveitar, porque sub-apps montados não rodam o próprio lifespan.
- [x] Playwright em threads: sem mudança, já estava certo (as tarefas rodam em threads do pool, sem event loop).
- [x] `celery` e `redis` removidos do `requirements.txt` (entrou `APScheduler==3.11.0`), stub do `celery` removido do `conftest.py`, `REDIS_URL` removido do `.env.example`.
- [x] `Dockerfile` e `docker-compose.yml` removidos **nesta fase** (antecipado da Fase 5): sem Celery, os serviços worker/beat não funcionavam mais.
- [x] Testes: `test_task_runner.py` (10), `test_scheduler.py` (11, incluindo `schedule_all_products`, `task_search_products` e o lifespan) e migração v1 → v2 + `AppMeta` no `test_db_client_sqlite.py`. Antes, com o Celery virando `MagicMock` no `conftest`, as tasks nunca eram exercitadas de verdade. Total: 172 testes passando.
- [x] Avisos de loja bloqueada voltaram a aparecer no `GET /search/{id}`.

**Validação real** (uvicorn em `127.0.0.1`, sem Celery/Redis importados):
- `POST /search` respondeu em 0,01 s; a busca rodou na thread `mv-task_0` e o `GET /search/{id}` trouxe `store_warnings = {"mercadolivre": "login_wall"}`. As duas lojas bloquearam nessa rodada (Amazon 503, ML login wall), então não vieram resultados; com as lojas liberadas, a gravação de resultados já tinha sido validada na Fase 2.
- `POST /monitor/add` respondeu em 0,03 s com `task_id`, o produto apareceu em `/products` e a checagem rodou em background, gravando no SQLite.
- Log: `Agendador iniciado ... próxima checagem completa=<agora + 1 min>` → `Checagem completa disparada`. Depois de reiniciar, a próxima ficou em última + 6h e os dados continuaram lá.

**Pronto quando:** sem Docker, `POST /monitor/add` grava o preço, `POST /search` + `GET /search/{id}` devolvem resultados, e o job de 6h aparece no log. ✅

---
### Fase 5: App único (backend + frontend num processo) ✅

**Objetivo:** `python main.py` abre o app completo no navegador.

- [x] `execution/desktop_app.py` (`create_app(web_dist)`):
  - `root = FastAPI(lifespan=web_server.lifespan)`: reaproveita o lifespan da Fase 4 (agendador + `task_runner`).
  - `root.mount("/api", web_server.app)`: rotas atuais intactas.
  - SPA (`SPAStaticFiles`): serve `apps/web/dist` (ou `web_dist/` no executável) e devolve o `index.html` para rotas do React Router. Caminho com extensão que não existe (ex: `/assets/x.js`) continua 404. O `index.html` vai com `Cache-Control: no-cache`, para o navegador pegar os assets novos depois de uma atualização.
  - Sem build do frontend: as páginas mostram como buildar (503) e a API continua respondendo em `/api`.
- [x] `main.py` (raiz) → `execution/launcher.py` (a lógica fica no pacote, que dá para testar):
  - **Instância única:** `DATA_DIR/app.lock` guarda `{pid, port}`; uma 2ª abertura confere `GET /api/` nessa porta e, se for o app, só abre o navegador e sai (~0,3 s). Lock antigo (app morto à força) é ignorado.
  - **Porta estável, não a 8000:** padrão **47290** (fora das portas comuns de dev e abaixo da faixa efêmera do Windows), e a última porta usada fica em `DATA_DIR/port` e é preferida nas próximas aberturas; `--port` sobrescreve. *Motivo:* o frontend guarda dados no `localStorage` (grupos de produtos, filtros do dashboard, estado do Zustand), que é separado por origem (host + porta). Nesta máquina a 8000 já estava ocupada, o app caiu numa porta aleatória e, na abertura seguinte, cairia em outra, e os grupos iriam "sumir".
  - Se a porta estiver ocupada (testado por conexão, porque no Windows o `bind` em 127.0.0.1 pode "funcionar" com outro programa em 0.0.0.0), usa uma livre. O socket já vinculado vai direto para o uvicorn (`server.run(sockets=[sock])`), sem corrida entre testar e usar.
  - Escuta só em `127.0.0.1`.
  - Abre o navegador assim que `GET /api/` responder (`--no-browser` desliga).
  - Logs: `DATA_DIR/logs/app.log` rotativo (1 MB × 3) + console; `httpx` em WARNING. No `.exe` sem console, `stdout`/`stderr` `None` viram `devnull`.
- [x] ~~Script `pnpm build:desktop`~~: não foi preciso. Em dev o `desktop_app` lê direto `apps/web/dist` (saída do `pnpm build`), e no executável o PyInstaller empacota essa pasta como `web_dist/` (`settings.WEB_DIST_DIR`, sobrescrevível por `MV_WEB_DIST`).
- [x] Remover `Dockerfile` e `docker-compose.yml` da branch `exe` (feito na Fase 4).
- [x] Testes: `test_desktop_app.py` (12, requisições ASGI diretas: SPA, fallback, assets, 404, `/api`, sem build) e `test_launcher.py` (28: health com servidor HTTP real, lock, porta estável, porta ocupada, navegador, 2ª abertura, log em arquivo). Total: 212.

**Validação real** (`python main.py --no-browser`, pasta de dados descartável, Firecrawl desligado; navegador do app):
- Dashboard, Produtos e Buscar renderizaram servidos pelo próprio app, sem erros no console. A navegação direta (F5) em `/products` e `/search` devolveu a página. `/api/*` devolveu JSON.
- Busca pela interface: `POST /api/search` → tarefa em background → a tela mostrou o aviso "Mercado Livre está temporariamente exigindo login" (as lojas seguiam bloqueando o scraping nesta rodada).
- Adicionar URL pela interface: `POST /api/monitor/add` → 200 → a tarefa em background cadastrou o produto, que apareceu na lista com a data local certa.
- 2ª abertura detectou a instância e saiu em ~0,3 s.
- Não foram exercitados nesta rodada (as lojas bloquearam o scraping): preço real, histórico com pontos, pausar/renomear/remover pela UI. As rotas correspondentes foram validadas na Fase 2.

**Decisões para a Fase 7, levantadas aqui:**
- ~~**Como o usuário fecha o app?**~~ **Decidido:** janela própria com o comportamento padrão de qualquer `.exe` (minimizar, restaurar, fechar). Fechar a janela encerra o app. Implementação na Fase 7 (`pywebview`).
- **Grupos de produtos no `localStorage`:** com a porta estável o risco caiu, mas os grupos ainda (1) não entram no backup do banco, (2) somem se o usuário limpar os dados do navegador ou trocar de navegador. Vale mover os grupos para o SQLite (tabela + rotas). Isso muda o frontend, então fica como tarefa própria.

**Pronto quando:** numa máquina com Python, mas **sem Docker/Postgres/Redis rodando**, `python main.py` abre o navegador, e dá para adicionar produto, ver histórico, buscar, pausar, renomear, remover e dar F5 em `/products` e `/search`. ✅ (com a ressalva acima sobre o que dependia das lojas)

> Este é o marco principal. Daqui em diante é empacotamento.

---
### Fase 6: Playwright e Firecrawl opcionais

**Objetivo:** o app funciona em qualquer máquina, mesmo sem Chromium baixado e sem chave do Firecrawl.

- [ ] `playwright_scraper.py`: ordem de tentativa do navegador:
  1. `channel="msedge"` (vem em todo Windows 10/11) ou `channel="chrome"`, se instalado;
  2. Chromium baixado em `BROWSERS_DIR` (`PLAYWRIGHT_BROWSERS_PATH`);
  3. nenhum disponível: retorna `None` com log e a cascata segue (o comportamento atual em caso de falha já é esse).
  - Descobrir o navegador uma vez e guardar o resultado, para não pagar a falha em toda chamada.
- [ ] Download do Chromium sob demanda (opcional na v1): rodar o driver embutido do Playwright (`playwright install chromium`) apontando para `BROWSERS_DIR`, disparado por uma ação explícita do usuário, nunca em silêncio.
- [ ] Firecrawl: já é ignorado sem chave. Documentar `FIRECRAWL_API_KEY` no `config.env` do usuário. **Nunca** embutir chave no build.
- [ ] Opcional: `GET /api/system/status` informando qual navegador está em uso e se o Firecrawl está configurado, para a UI mostrar isso depois.
- [ ] **Ferramenta de dev: copiar os dados da versão web para testes** (`scripts/copy_web_data.py`). Lê o Postgres da versão web (subido pelo `docker-compose` da `main`) **só com SELECT**, e grava num SQLite **novo** numa pasta escolhida (ex: `MV_DATA_DIR=.data/copia-web`), nunca na pasta padrão do app nem por cima de um banco existente. Copia `Product`, `PriceHistory` e, opcionalmente, `SearchResult`, mantendo ids e datas (convertidas para o formato ISO UTC do `db_client`). Não entra no executável; serve para você e para as validações terem dados reais.

**Pronto quando:** com Edge, sem Chromium do Playwright e sem chave do Firecrawl, um produto que exige JS (nível 2) é capturado.

---

### Fase 7: Empacotamento com PyInstaller

**Objetivo:** pasta `dist/MelhoresValores/` com `MelhoresValores.exe` que roda numa máquina limpa.

- [ ] **Janela nativa (decidido: comportamento padrão de `.exe`: minimizar, restaurar, fechar)** com `pywebview`, que no Windows usa o Edge WebView2, já presente no Windows 10/11. Pode ser validada com `python main.py` antes do PyInstaller:
  - O uvicorn roda numa thread; a janela (`webview.create_window` apontando para `http://127.0.0.1:<porta>/`) fica na thread principal. **Fechar a janela** para o uvicorn, e o `lifespan` desliga agendador e fila.
  - **`private_mode=False` + `storage_path=<pasta de dados>/webview`**: o padrão do pywebview é modo privado, que apagaria o `localStorage` (grupos, filtros) a cada abertura.
  - 2ª abertura: em vez de abrir o navegador, pede à instância aberta para trazer a janela para frente (rota local só do `desktop_app`, fora de `/api`).
  - `--browser` (dev) mantém o modo atual, que abre no navegador padrão.
  - Título "Melhores Valores", ícone, tamanho mínimo, e lembrar tamanho/posição da janela (opcional).
  - Sem WebView2 (Windows antigo): mensagem explicando como instalar, ou cair para o navegador padrão.
- [ ] **Executável sem dados do dev:** o `.spec` não pode incluir `.env`, `*.db` nem `.data/`. O `settings.py` já não carrega o `.env` do repo quando `is_frozen()` (feito, com teste). Conferir na Windows Sandbox que a 1ª abertura cria um banco vazio e que não há chave do Firecrawl configurada.
- [ ] `packaging/melhores_valores.spec` (versionado, em vez de linha de comando):
  - `--onedir` (abre mais rápido e gera menos alerta de antivírus que `--onefile`).
  - `datas`: `apps/web/dist` → `web_dist` (é onde `settings.WEB_DIST_DIR` procura quando `is_frozen()`).
  - `hiddenimports`: submódulos do `uvicorn` (`uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`, ...) e `apscheduler`. `lxml` e `playwright` têm hooks no `pyinstaller-hooks-contrib`.
  - Inclui o driver do Playwright, mas **não** os navegadores.
  - `console=False` e ícone (a janela é a do `pywebview`, não um terminal).
- [ ] `scripts/build_desktop.ps1` (e `.sh`): `pnpm build` → `pyinstaller packaging/melhores_valores.spec`.
- [ ] Testar na **Windows Sandbox** (vem no Windows 11 Pro e é uma máquina limpa descartável, sem Python/Node/Docker): abrir, adicionar produto, fechar, reabrir e conferir se o histórico continua lá.
- [ ] Opcional: instalador com Inno Setup (atalho no menu Iniciar, desinstalador).

**Pronto quando:** o `.exe` funciona na Windows Sandbox.

---

### Fase 8: Build multiplataforma e distribuição

- [ ] **Botão para checar o preço de novo dentro dos itens** (a checagem automática só roda com o app aberto, então o usuário precisa disparar na hora que quiser). Fica para o final, antes da release. *A definir com você:* hoje a lista de produtos já tem "Atualizar preço" por item (`POST /product/{id}/refresh`). O pedido é (a) levar esse botão também para dentro do modal de detalhes do item, (b) um "Atualizar todos", ou (c) refazer a **busca por nome** de um item?
- [ ] `.github/workflows/build-desktop.yml`: disparado por tag `v*`, matriz `windows-latest` / `macos-latest` / `ubuntu-latest` (o PyInstaller não faz cross-compile), roda os testes, faz o build e anexa os `.zip` ao **GitHub Release**.
- [ ] **README novo para a versão .exe, sem substituir o `README.md` atual** (que continua descrevendo a versão servidor/Docker): criar `README-EXE.md` na raiz e linkar a partir do `README.md`. Conteúdo: o que é a versão desktop e como difere da servidor, download pelo GitHub Releases, instalação e primeira execução, aviso do SmartScreen ("Mais informações → Executar assim mesmo"), onde ficam os dados (`%LOCALAPPDATA%\MelhoresValores\`) e como fazer backup, `config.env` (chave opcional do Firecrawl), navegador usado pelo scraping (Edge/Chrome/Chromium), limitações (checagem só com o app aberto), como gerar o build a partir do código e solução de problemas (porta ocupada, logs). Escrito no final, quando o comportamento já estiver fechado.
- [ ] Versão única em `execution/__init__.py` (`__version__`), usada no build e na checagem de atualização.

**Pronto quando:** criar a tag `v0.1.0` gera um Release com os 3 artefatos.

---

### Fase 9: Pós-v1 (melhorias, fora do escopo inicial)

- Checagem de nova versão na abertura (API do GitHub Releases), com aviso na UI.
- Opcional: ícone na bandeja (`pystray`) para continuar agendando com a janela fechada, mais "iniciar com o sistema". Na v1, fechar a janela encerra o app (decidido).
- Tela de configurações (chave do Firecrawl, intervalo de checagem, baixar Chromium).
- Backup/exportação do banco (o banco é um arquivo, então basta copiar).

---

## 5. Ordem e dependências

```
F0 ─► F1 ─► F2 (banco) ─┐
            F3 (cache) ─┼─► F5 (app único) ─► F6 (opcionais) ─► F7 (exe) ─► F8 (release) ─► F9
            F4 (fila)  ─┘
```

F2, F3 e F4 são independentes entre si (cada uma troca um serviço) e podem ser feitas em qualquer ordem, uma por PR. Fazer F2 primeiro: é a maior e a de maior risco.

## 6. Decisões tomadas (e por quê)

| Decisão | Alternativa descartada | Motivo |
| --- | --- | --- |
| `sqlite3` + modelos Pydantic | SQLAlchemy | 3 tabelas, acesso já centralizado, zero dependência nova, e os objetos ficam com a mesma "cara" dos do Prisma |
| Shim `@task` com `.delay()` | Chamar `executor.submit` direto nas rotas | `web_server.py` e testes não mudam |
| API em `/api` + SPA na raiz | API na raiz + `VITE_API_URL` relativo | Evita a colisão `/products` e `/search` entre SPA e API, e o frontend não muda |
| Janela nativa com `pywebview` (decidido na F5) | Navegador padrão / Tauri / Electron | Comportamento padrão de `.exe` (minimizar, restaurar, fechar = sair); reaproveita o WebView2 do Windows, sem embutir um navegador como o Electron |
| Testador começa zerado | Distribuir com dados de exemplo | Pedido explícito; banco vazio na 1ª abertura e nenhuma chave do dev no build |
| Edge do sistema primeiro | Embutir Chromium | Evita ~150 MB no Windows |
| Só modo desktop na branch `exe` | Manter modo servidor e desktop juntos por flag | Manter dois modos dobra a manutenção; o modo servidor continua vivo na `main` |

## 7. Riscos

| Risco | Mitigação |
| --- | --- |
| SQLite com escrita concorrente (API + 2 workers + agendador) | WAL, `busy_timeout`, lock de escrita no `db_client` |
| Diferença de comportamento Postgres → SQLite (NULLs, datas, mediana) | Testes reais do `db_client` (Fase 2) cobrindo exatamente esses casos |
| Antivírus/SmartScreen bloqueando `.exe` não assinado | `--onedir`, aviso no README; assinatura de código é paga (avaliar depois) |
| Adapters quebram quando as lojas mudam o HTML | Correções feitas na `main` entram via `git merge main` (arquivos não tocados) + checagem de versão (F9) |
| Agendamento só com o app aberto | Recuperação na abertura (F4) + botão para checar de novo nos itens (F8) + bandeja opcional (F9) |
| Termos de uso das lojas | Já existe hoje; distribuir aumenta a exposição. Manter frequência conservadora (6h) |

## 8. Documentação a atualizar na branch `exe`

- `CLAUDE.md`, `AGENTS.md`, `docs/architecture.md`, `docs/stack.md`, `docs/flows.md`: sem Docker/Celery/Redis/Prisma.
- Diretivas `01_database_prisma.md` (→ SQLite), `03_task_queue_and_scheduler.md` (→ threads/APScheduler), `05_caching_rules.md` (→ memória).

**Já atualizados (F2–F4):** `CLAUDE.md`, `AGENTS.md`, `execution/README.md`, `docs/stack.md`, `docs/conventions.md`, diretivas 01, 03 e 05.
**Ainda desatualizados (revisão final de docs, junto com o `README-EXE.md`):** `docs/architecture.md`, `docs/flows.md`, `docs/ci.md`, diretivas `06_vision_project.md` e `07_automatic_search.md`, `.agents/workflows/arquitetura.md`, `execution/scrapers/README.md` (Chromium no Docker). O `README.md` raiz **não é alterado**: continua descrevendo a versão servidor.

## 9. Checklist geral

- [x] F0 Preparação da branch
- [ ] F1 `settings.py` e pasta de dados (parcial: `DATA_DIR`/`DB_PATH`/config prontos)
- [x] F2 `db_client.py` em SQLite + `models.py` + testes reais
- [x] F3 Cache e status de busca em memória (remoção do pacote `redis` fica para a F4)
- [x] F4 `task_runner.py` + APScheduler com recuperação na abertura
- [x] F5 `desktop_app.py` + `main.py`, validado sem Docker
- [ ] F6 Playwright via Edge/Chrome do sistema, Firecrawl opcional, script para copiar os dados da web (só leitura)
- [ ] F7 Janela nativa (pywebview), PyInstaller `--onedir` sem dados do dev, testado na Windows Sandbox
- [ ] F8 Botão para checar o preço de novo nos itens, workflow multiplataforma + GitHub Release + `README-EXE.md` (novo, o `README.md` atual fica)
- [ ] F9 Atualizações, bandeja (opcional), configurações
