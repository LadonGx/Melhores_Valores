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

### Fase 1: Configuração e pasta de dados ✅ (completada ao longo das Fases 5–7)

**Objetivo:** um lugar só para caminhos e configuração, funcionando em dev e no executável.

Novo `execution/settings.py`:
- [x] `DATA_DIR`: `platformdirs.user_data_dir("MelhoresValores", appauthor=False)`, sobrescrevível pela env `MV_DATA_DIR` (útil em dev e nos testes).
- [x] `DB_PATH` (sobrescrevível por `MV_DB_PATH`). A pasta é criada pelo `db_client` na primeira conexão, para o import não criar pastas.
- [x] Carrega `DATA_DIR/config.env` (prioridade) e o `.env` do repo com `python-dotenv`.
- [x] `LOG_DIR`, `LOCK_PATH`, `PORT_PATH` (F5), `BROWSERS_DIR` (F6), `WEBVIEW_DIR` (F7).
- [x] `is_frozen()` e `resource_path()` para achar o `web_dist` dentro do pacote do PyInstaller (`sys._MEIPASS`) (F5); no executável, o `.env` do repo nunca é carregado.

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
### Fase 6: Playwright e Firecrawl opcionais ✅

**Objetivo:** o app funciona em qualquer máquina, mesmo sem Chromium baixado e sem chave do Firecrawl.

- [x] `playwright_scraper.py`: ordem de tentativa do navegador:
  1. `channel="msedge"` (vem em todo Windows 10/11), depois `channel="chrome"`;
  2. Chromium do próprio Playwright (em dev, `playwright install chromium`; no executável, procurado em `BROWSERS_DIR`, via `PLAYWRIGHT_BROWSERS_PATH`);
  3. nenhum disponível: retorna `None`, registra **uma vez** no log e a cascata segue.
  - A escolha é feita na 1ª chamada (com lock entre threads) e lembrada no processo (`browser_in_use()`). Se o navegador lembrado parar de abrir (ex: desinstalado), a escolha é esquecida e a próxima chamada detecta de novo. Argumentos de lançamento (headless, anti-automação) iguais aos de antes.
  - Vale também para a busca do Mercado Livre, que usa a mesma `fetch_html_playwright`.
- [ ] Download do Chromium sob demanda: **não feito** (opcional na v1). No Windows o Edge sempre existe. Em macOS/Linux sem Chrome, o nível 2 fica desligado até essa opção existir; avaliar quando houver testadores fora do Windows.
- [x] Firecrawl: já era ignorado sem chave. O executável não carrega mais o `.env` do repo (feito antes da F6, com teste), então só funciona com a chave que o próprio usuário puser em `<pasta de dados>/config.env`. **Nunca** embutir chave no build. A documentação para o usuário entra no `README-EXE.md` (F8).
- [ ] Opcional: `GET /api/system/status` (navegador em uso, Firecrawl configurado): **não feito**. `browser_in_use()` já existe para quando a UI precisar.
- [x] **Ferramenta de dev: copiar os dados da versão web para testes** (`scripts/copy_web_data.py`):
  - Lê o Postgres da versão web com `psycopg` numa transação **READ ONLY** (só `SELECT`; qualquer escrita falharia no servidor). A URL padrão vem do `DATABASE_URL` do `.env`, sem os parâmetros que só o Prisma entende.
  - Grava num SQLite **novo** (padrão `.data/copia-web/`, que está no `.gitignore`). Se o arquivo já existir, aborta antes até de ler o Postgres. A gravação é via `db_client.bulk_import` (nova função; recusa banco que já tenha dados) numa transação única, tudo ou nada.
  - Preserva ids e datas. Os timestamps do Prisma (sem fuso, em UTC) são marcados como UTC: sem isso, iriam para o SQLite deslocados em -3h.
  - `--with-search-results` (opcional), `--dry-run` (só conta). `psycopg[binary]` entrou só no `requirements-dev.txt`; não vai para o executável.
  - **Cópia real feita** (com o container ligado por você): 21 produtos, 705 registros de histórico e 277 resultados de busca em `.data/copia-web/`. As contagens e o último `scrapedAt` conferem exatamente com o Postgres, sem deslocamento de fuso. Esta cópia fica intacta; os testes manuais usam uma cópia dela.
- [x] Testes: escolha do navegador (6 casos: Edge, fallback para Chrome, para Chromium, nenhum, navegador que some), `settings` no modo executável (4), `bulk_import`/`is_empty` (3) e o script de cópia (10: só leitura, destino existente, fuso, dry-run, Postgres fora do ar). Total: 234.

**Validação real** (Firecrawl desligado):
- Página de busca da Amazon pelo nível 2: abriu com o **Microsoft Edge** (detectado na 1ª chamada), 1,7 MB de HTML com resultados em 6 s. Pelo `httpx` (nível 1) essa mesma página devolvia 503.
- Produto da Amazon extraído pelo nível 2 com o Edge: nome, R$ 66,41, em estoque, confiança 0,92, em 12 s.

**Comparativo httpx × Edge × Chrome × Chromium do Playwright** (o jeito anterior à F6), com os produtos reais copiados da versão web. 8 produtos (4 Amazon, 4 Mercado Livre) e 2 páginas de busca, 3 rodadas intercaladas (a ordem dos métodos gira para ninguém ter vantagem), pausa de 2–4 s entre requisições, Firecrawl desligado, worker da versão web desligado:

| | httpx (nível 1) | Edge | Chrome | Chromium (anterior) |
| --- | --- | --- | --- | --- |
| Produtos Amazon (preço extraído) | 10/12 (2 falhas de parse) | **12/12** | **12/12** | 11/12 |
| Busca Amazon (60 resultados por rodada) | 1/3 | **3/3** | **3/3** | 1/3 (bloqueado a partir da 2ª rodada) |
| Produtos Mercado Livre | 0/12 (`login_wall`) | 0/12 (`login_wall`) | 0/12 (`login_wall`) | 0/12 (`login_wall`) |
| Busca Mercado Livre | 0/3 | 0/3 | 0/3 | 0/3 |
| Tempo (mediana, produto) | 0,8 s | 11,9 s | 11,8 s | 12,5 s |

Conclusões:
- **O Edge (e o Chrome) foram melhores que o Chromium do Playwright**, e não o contrário. Na página mais vigiada, a busca da Amazon, o Chromium foi bloqueado depois da 1ª rodada, enquanto Edge e Chrome passaram nas 3. O bloqueio olha a "cara de robô" do navegador e o IP/ritmo, não a marca. O Chromium que vem com o Playwright é o mais fácil de identificar como automação.
- **Usar o Chromium como alternativa "se o Edge for bloqueado" não ajudaria:** mesmo IP, navegador mais detectável. Por isso a ordem Edge → Chrome → Chromium fica como está. O Chromium continua só como reserva para **máquina sem Edge/Chrome** (ou Edge que não abre), não para contornar bloqueio. Não vale implementar troca automática de navegador ao detectar bloqueio: dobraria o tráfego sem chance real de passar.
- **O nível 1 (`httpx`) continua valendo a pena:** resolve a maioria dos produtos da Amazon em 0,8 s, contra ~12 s de um navegador, e o Edge cobre as falhas.
- **Mercado Livre:** bloqueado (`login_wall`) para todos os métodos, inclusive o `httpx`. É bloqueio por sessão/IP, e trocar de navegador não resolve. Na cascata o Firecrawl é pulado nesse caso, como já era. Contornar exigiria sessão logada do usuário, fora do escopo.
- A única divergência de preço (Ogros-Deuses: 103,66 × 79,90 só na 1ª rodada) não tem relação com o navegador: o histórico da versão web também alterna entre esses dois valores. A Amazon mostra ofertas diferentes para esse item (seletores diferentes, confiança 0,96 × 0,92). É um ponto do adapter da Amazon, que já existe na versão web.
- Possível reforço futuro (não testado): o scraper fixa o user-agent em "Chrome 124", mas o Edge do sistema é bem mais novo. Essa diferença entre o user-agent e os client hints é um sinal que alguns anti-bots usam. Com navegador do sistema, não fixar o user-agent deixaria a assinatura coerente.

**Teste manual no app com os dados copiados** (`.data/teste-manual`, cópia da cópia; Firecrawl desligado):
- 21 produtos, 2 promoções, modal de detalhes com estatísticas e gráfico de 30 dias, tudo do SQLite copiado.
- A checagem de recuperação (1 min após abrir) enfileirou os 20 ativos: 12/12 da Amazon com preço (11 pelo nível 1; **o Echo Dot 5ª geração falhou no nível 1 e foi capturado pelo Edge no nível 2, R$ 649,00**) e 8/8 do Mercado Livre com `login_wall` no Edge, Firecrawl pulado.
- "Atualizar preço" pela lista (`POST /api/product/{id}/refresh`) → 200, R$ 638,99. O modal de detalhes **não** tem botão de atualizar (relevante para o botão pedido para o final).

**Busca da Amazon com fallback para o nível 2** (feito só na `exe`, a pedido): `search_amazon` tenta o `httpx` e, se não vier **nenhum card** (erro, 503 ou página de verificação com status 200), abre a mesma URL com `fetch_html_playwright` (Edge/Chrome), esperando o seletor dos cards. O parser dos cards foi separado (`_parse_results`) e serve aos dois níveis. 6 testes novos: 503 → navegador, página sem cards → navegador, navegador não é usado quando o `httpx` funciona, navegador sem cards → `[]`, `max_results` no nível 2, falha total → `[]`.
- Real: "echo dot", "o caminho dos reis" e "mouse logitech m170" voltaram com 10/10/6 resultados, todos pelo nível 2 (de 6 a 11 s). No app, pela interface: `httpx` com 503 → Edge → 10 resultados da Amazon em 5 s, listados por preço junto com o aviso de bloqueio do Mercado Livre.

**Achado importante: o Playwright 1.44 do projeto está velho demais para os navegadores atuais.**
- No dia seguinte ao comparativo, o Edge 155 passou a fechar **0,03 s depois de aberto pelo Playwright 1.44** (5 de 5 vezes no terminal, código de saída 0), até com janela visível. O Edge abre normalmente fora do Playwright. O Chrome 155 continuou funcionando, e minutos depois o Edge voltou a abrir dentro do app. Ou seja: falha **intermitente**, de compatibilidade (o 1.44 é de maio/2024 e suporta oficialmente o Chromium 125).
- Num ambiente Python separado, com o **Playwright 1.64.0**, o mesmo Edge 155 abriu 3 de 3 vezes, em ~2 s (o 1.44 levava ~6 s para abrir a busca).
- Por que importa: muitos testadores Windows só têm o Edge. Com o 1.44, o nível 2 pode simplesmente não funcionar para eles, e o executável não teria como se recuperar.
- **Feito: Playwright atualizado para 1.64.0** (só no `requirements.txt` da `exe`; a versão web usa o Dockerfile da `main` e não muda). `pip check` sem conflitos (vieram junto `greenlet` 3.5.6 e `pyee` 14), código sem mudança de API, 239 testes passando. Validação real com o 1.64:
  - Edge aberto e fechado 10 vezes pelo mesmo caminho do app (`_launch`): **10/10**, 0,8 s em média (com o 1.44: 0/5 nessa mesma manhã).
  - Produtos reais pelo nível 2 com detecção automática: 4/4 da Amazon com preço pelo **Edge**; Mercado Livre `login_wall`, como antes.
  - Busca da Amazon: "echo dot" pelo `httpx` (1,7 s); "o caminho dos reis" e "x-men exterminio" levaram 503 no `httpx` e vieram pelo Edge (10 resultados cada, ~6 s).
  - No app, pela interface: busca "x-men exterminio" → Edge → 10 resultados (o sem preço no fim). **Monitorar** num resultado → produto cadastrado com o preço da busca (R$ 26,90) → a checagem em background confirmou R$ 26,90 pelo Edge no nível 2, sem duplicar o registro.
  - Atenção (só em dev): o Chromium do próprio Playwright, a última reserva, precisa ser baixado de novo para o 1.64 (`playwright install chromium`; o que está instalado é o do 1.44). Não baixei. O executável não usa esse Chromium (Edge/Chrome do sistema), então isso só importa para quem desenvolve numa máquina sem Edge e sem Chrome.
- Proteção já aplicada: sem navegador nenhum, o nível 2 não fica mais desligado até reiniciar o app; tenta detectar de novo depois de 10 min (`RETRY_DETECTION_AFTER`), com teste.

> **Achado para depois (UX):** a fila tem 2 threads e é compartilhada. Quando a checagem automática enfileira os 20 produtos (ex: 1 min depois de abrir, se a última foi há mais de 6 h), uma busca feita pelo usuário espera atrás deles, e no Mercado Livre bloqueado cada item leva ~30 s. Vale dar prioridade às ações do usuário (busca, adicionar produto, o botão de checar de novo) com uma fila separada ou com prioridade. Entra junto com o botão da F8.

**Pronto quando:** com Edge, sem Chromium do Playwright e sem chave do Firecrawl, um produto que exige JS (nível 2) é capturado. ✅

---
### Fase 7: Janela nativa e empacotamento com PyInstaller ✅

**Objetivo:** pasta `dist/MelhoresValores/` com `MelhoresValores.exe` que roda numa máquina limpa.

- [x] **Janela nativa** (`pywebview==6.2.1`, que usa o Edge WebView2 do Windows) em `launcher.run_with_window`:
  - Servidor (uvicorn) numa thread; a janela na thread principal, como o pywebview exige. Só abre depois de o servidor responder. **Fechar a janela** para o servidor, e o `lifespan` desliga agendador e fila.
  - `private_mode=False` + `storage_path=<pasta de dados>/webview` (`settings.WEBVIEW_DIR`), porque o padrão do pywebview é modo privado.
  - `background_color` igual ao do app (`#0f1117`, sem flash branco ao abrir) e `text_select=True` (o padrão do pywebview impede selecionar e copiar texto). Tamanho 1280×820, mínimo 960×640.
  - 2ª abertura: `POST /_desktop/focus` (rota do `desktop_app`, fora de `/api`, registrada antes do mount do frontend) restaura e traz a janela para frente.
  - Modos: padrão = janela; `--browser` = navegador padrão; `--no-browser` = só o servidor. Sem WebView2, cai para o navegador padrão.
  - `main.py` encerra com `os._exit` depois do `main()`: uma checagem em andamento deixaria o processo vivo e invisível por até ~30 s depois de fechar a janela (o SQLite desfaz a escrita interrompida).
  - Não feito (opcional): lembrar o tamanho e a posição da janela.
- [x] **Executável sem dados do dev:** o `.spec` só inclui o código, o `web_dist` e o driver do Playwright. O `scripts/build_desktop.ps1` **falha o build** se aparecer `.env`, `config.env` ou `*.db*` na pasta gerada. O `settings.py` não carrega o `.env` do repo no executável (com teste).
- [x] `packaging/melhores_valores.spec`: `--onedir`, `console=False`, sem UPX (falso positivo de antivírus), ícone, `datas` = `apps/web/dist` → `web_dist`, `hiddenimports` = submódulos do `uvicorn` + backend asyncio do `anyio`, `excludes` de ferramentas de dev. Aborta com mensagem clara se faltar o `pnpm build`.
  - Ajuste preventivo: o agendador passou a usar `IntervalTrigger(...)` em vez do texto `"interval"`, que o APScheduler resolve por entry points que o PyInstaller não leva.
- [x] `packaging/icon.ico` (selo "MV" da barra lateral, na cor `--color-primary`), gerado por `packaging/make_icon.py`.
- [x] `scripts/build_desktop.ps1`: `pnpm build` → PyInstaller → checagem de vazamento → tamanho. `pyinstaller==6.22.3` no `requirements-dev.txt`; `pywebview==6.2.1` no `requirements.txt`. `/build/` e `/dist/` no `.gitignore`.
- [x] Testes: janela (armazenamento persistente, fechar encerra o servidor, sem WebView2 → navegador, servidor que não sobe → sem janela, trazer para frente), 2ª abertura (foca a janela / abre o navegador / `--browser`), rota de foco (404 sem janela, chama o handler, não é engolida pelo SPA) e regressão do log em cp1252. Total: 253.
- [ ] ~~Testar na Windows Sandbox~~: **descartado por decisão sua** (o recurso não está habilitado nesta máquina). O `scripts/sandbox_test.ps1` fica para quem quiser usar. No lugar, o `.exe` foi testado com pasta de dados vazia, persistência entre aberturas e troca de versão (F8).
- [ ] Opcional: instalador com Inno Setup (atalho no menu Iniciar, desinstalador).
- Possível enxugamento (não feito): `cryptography` (8 MB) e `PIL` (5 MB) entram por imports opcionais de dependências. Dá para excluir depois de confirmar que nada os usa em tempo de execução.

**Validação real:**
- `python main.py`: a janela abriu com o dashboard e as imagens dos produtos. **Minimizar** + abrir o app de novo → a janela voltou para frente (2ª abertura saiu em 0,3 s). **Fechar** pelo X → app encerrado em 0,2 s, lock apagado, porta liberada.
- `localStorage` entre aberturas: a 1ª abertura gravou um valor pelo próprio WebView2, a 2ª leu o mesmo valor.
- **Build:** `dist\MelhoresValores\MelhoresValores.exe`, 165 MB na pasta (102 MB são o driver do Playwright: Node + Playwright; o frontend ocupa 0,8 MB).
- **Bug encontrado só no `.exe` e corrigido:** sem console, o `stderr` era um arquivo nulo em cp1252. O log "migração v0 **→** v1" levantava `UnicodeEncodeError`, que no Python 3.12 escapa do handler para o chamador. A migração era abortada e todas as consultas falhavam. Correção: `devnull` em UTF-8, `reconfigure(errors="backslashreplace")` e `logging.raiseExceptions = False` (falha de log nunca derruba o app). Teste de regressão incluído.
- **`.exe` como testador novo** (pasta de dados vazia, aberto a partir da raiz do repo, onde está o `.env`): banco criado do zero (v2, 0 produtos, 0 histórico), API e frontend ok, sem erros no log. Busca "echo dot": 503 no `httpx` → **driver do Playwright empacotado abriu o Edge** → 10 resultados. Monitorar → produto gravado. Janela com o ícone "MV"; fechar → processo encerrado, lock apagado, **nenhum Edge headless órfão**.

**Pronto quando:** o `.exe` funciona na Windows Sandbox. → Funciona numa pasta de dados vazia nesta máquina; o teste em máquina limpa depende de habilitar o Sandbox.

---
### Fase 8: Botões de checagem, build automático, release e README-EXE ✅

- [x] **Botões para checar de novo** (decidido: botão nos detalhes + "Atualizar todos"; não foi pedido refazer a busca por nome):
  - **"Atualizar preço agora" dentro dos detalhes do item** (`RefreshPriceButton`), também em cada anúncio de um grupo. Mostra o resultado ao lado ("Preço atualizado: R$ 72,19", ou o motivo do bloqueio) e revalida na hora o gráfico, as estatísticas e a tabela do modal (o `useRefreshPrice` agora invalida também `['product', id]`).
  - **"Atualizar todos"** (`RefreshAllButton`, no Dashboard e em Produtos): `POST /api/products/refresh-all` inicia um lote com todos os produtos ativos, **sem cache**; `GET /api/products/refresh-all` devolve o progresso (`total/done/ok/failed`). O botão mostra "Atualizando 3/21…", a lista se atualiza a cada produto concluído e, no fim, aparece um aviso com o resumo.
  - **A checagem automática de 6 h usa o mesmo lote** (`schedule_all_products(trigger="agendada")`), então a tela também mostra quando o app está checando sozinho. Não há lote duplicado: apertar o botão durante a checagem automática mostra o progresso dela. O horário da última checagem completa é gravado num lugar só, e um "Atualizar todos" manual também zera o relógio de 6 h.
  - Mensagens de resultado centralizadas em `features/products/refreshMessages.ts` (a página Produtos usava uma cópia embutida).
- [x] **Fila com prioridade** (achado da Fase 6): `task_runner` tem duas filas de 2 threads, `user` (busca, adicionar produto) e `background` (lotes). `Task.apply_async(..., queue="background")` como no Celery. Teste: uma ação do usuário termina na hora com a fila de lote lotada.
- [x] **Versão:** `execution/__init__.py` → `__version__ = "0.1.0"`, exposta no `GET /api/` e no log de abertura.
- [x] **Workflow `.github/workflows/build-desktop.yml`** (Windows): tag `vX.Y.Z` → confere se a tag bate com o `__version__`, roda os testes (Python + frontend), gera o build com `scripts/build_desktop.ps1` (com a checagem de vazamento), compacta e cria o **Release em rascunho** (`prerelease`), para você revisar e publicar. Execução manual gera só o artefato.
  - Decisão: **só Windows por enquanto** (o plano previa Windows/macOS/Linux). A janela usa o WebView2 do Windows; macOS/Linux exigem outras dependências nativas do pywebview, além de assinatura/notarização no macOS, e ainda não há testadores nesses sistemas.
- [x] **`README-EXE.md`** (novo; o `README.md` só ganhou um link para ele): o que é e como difere da versão web, requisitos, instalar e abrir (SmartScreen), primeiro uso, atualizar preços, onde ficam os dados (backup, atualizar de versão, desinstalar), Firecrawl opcional com `config.env`, limitações, solução de problemas e a seção para desenvolvedores (build, release).
- [x] Testes: backend 267 (filas, lote com progresso, não duplicar, sem produtos, rotas `refresh-all`); frontend 43 (mensagens, `useRefreshAll`: progresso, fim do lote, abertura com lote já terminado; `RefreshPriceButton`: preço, bloqueio, timeout). `pnpm lint` e `pnpm typecheck` limpos.

**Validação real** (app com a cópia dos seus dados; Firecrawl desligado):
- "Atualizar todos" no Dashboard: 21 produtos ativos (o pausado ficou de fora), concluído em 2 min 16 s, **13 ok** (Amazon) e **8 falhas** (Mercado Livre com `login_wall`). O botão mostrou "Atualizando 1/21…" e no fim o aviso "Checagem concluída: 13 de 21 atualizados · 8 não puderam ser verificados agora". A lista foi atualizando sozinha.
- Durante o lote, uma busca rodou na fila `user` (`mv-user_0`) com as duas threads `mv-background` ocupadas, sem esperar.
- "Atualizar preço agora" no modal: "Preço atualizado: R$ 72,19", o card de preço atual mudou (63,71 → 72,19), o preço médio foi recalculado e um ponto novo apareceu no gráfico.
- **Persistência com o `.exe` reconstruído** (pasta de dados vazia): abriu com 0 produtos → adicionou 2 → fechou pelo X → reabriu: 2 → "versão nova" em outra pasta, mesma pasta de dados: 2 → o usuário excluiu 1 → reabriu: 1. O que o usuário adiciona só some se ele excluir.

---
### Fase 9: Pós-v1 — aviso de versão, Sobre/Diagnóstico e grupos no banco ✅

Escolhidos por você (pensando nos testadores): **aviso de versão nova**, **tela Sobre/Diagnóstico** e **grupos no banco**. Ficaram de fora: configurações e backup.

- [x] **Grupos de produtos no SQLite** (antes só no `localStorage`): migração **v3** (`ProductGroup` + `ProductGroupMember`, com `ON DELETE CASCADE` e a ordem dos anúncios). `db_client`: `list_groups`, `create_group`, `update_group`, `delete_group`, `import_groups`. Rotas `GET/POST /api/groups`, `PATCH/DELETE /api/groups/{id}`, `POST /api/groups/import`.
  - Mesma regra de antes, agora no backend: grupo precisa de 2+ produtos existentes. Ao excluir um produto, ele sai dos grupos, e o grupo que fica com 1 anúncio é desfeito.
  - O hook `useProductGroups` manteve a interface (o Dashboard não mudou). Na 1ª abertura, envia ao backend os grupos que ainda estiverem no `localStorage` (preservando id, nome e data) e apaga a cópia local. Se falhar, guarda para tentar de novo. A importação é idempotente.
  - Validação: na cópia dos seus dados, a migração v2 → v3 rodou; um grupo gravado à moda antiga foi migrado com a data original; depois de **apagar todo o `localStorage`** o grupo continuou na tela.
- [x] **Aviso de versão nova:** `execution/system_info.py` consulta `api.github.com/repos/LadonGx/Melhores_Valores/releases` (repositório público, sem login), ignora rascunhos, conta pré-releases (como o workflow publica) e compara vX.Y.Z numericamente. Cache de 6 h (limite de 60 consultas/hora sem login). Falha de rede nunca vira erro. `GET /api/system/update` (`?force=true` ignora o cache). No frontend, uma faixa no topo ("Nova versão disponível: 0.2.0 · Baixar →"), dispensável por versão. O link abre no navegador padrão (o pywebview repassa `target="_blank"`, o mesmo que já valia para "Ver anúncio →").
- [x] **Tela Sobre** (item "Sobre" na barra lateral, rota `/about`): versão + status de atualização + "Verificar agora"; diagnóstico (navegador do nível 2, Firecrawl ligado/desligado, última checagem completa, sistema, pasta de dados, arquivo de log); **"Abrir pasta de dados"** e **"Abrir pasta de logs"** (`POST /api/system/open-folder`, só esses dois destinos); **"Copiar diagnóstico"** (API de área de transferência → `execCommand('copy')` → se tudo falhar, o texto aparece numa caixa para copiar com Ctrl+C). `GET /api/system/info`; versão também no `GET /api/`.
- [x] Testes: backend 296 (grupos: criar, ordem, inválidos, renomear, desfazer com <2, exclusão de produto, importação idempotente, upgrade v2 → v3; verificação de versão: parse, rascunho/pré-release, rede fora, cache/force; diagnóstico; rotas de grupos e sistema). Frontend 59 (migração do `localStorage`, hook de grupos, faixa de versão nova, texto do diagnóstico, cópia com fallback).
- Achado durante a validação, **graças à própria tela Sobre**: no PowerShell, `$env:FIRECRAWL_API_KEY = ""` **apaga** a variável, e aí o `.env` do repo voltava a ser carregado nas minhas validações em dev. Nenhuma chamada ao Firecrawl apareceu nos logs dessas rodadas (o único crédito gasto continua sendo o da Fase 4). Correção: uma chave só com espaços conta como "sem chave", e as validações passaram a usar `" "`. No executável isso nunca aconteceria, porque ele não lê o `.env` do repo.
- **Não verificado na janela real:** o "Copiar diagnóstico" dentro da janela do WebView2 (a ferramenta de captura de tela escondia o conteúdo da janela). No painel de navegador a cópia foi negada e a mensagem de falha apareceu. Os três caminhos da cópia têm teste automatizado.
- Ideias que continuam em aberto: configurações (chave do Firecrawl e intervalo pela tela), backup/exportação pela tela, bandeja do sistema, lembrar o tamanho da janela, user-agent coerente com o Edge, prioridade entre ofertas da Amazon.
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
**Ainda desatualizados (revisão final de docs):** `docs/architecture.md`, `docs/flows.md`, `docs/ci.md`, diretivas `06_vision_project.md` e `07_automatic_search.md`, `.agents/workflows/arquitetura.md`, `execution/scrapers/README.md` (Chromium no Docker). O `README.md` raiz **não é alterado**: continua descrevendo a versão servidor.

## 9. Checklist geral

- [x] F0 Preparação da branch
- [x] F1 `settings.py` e pasta de dados
- [x] F2 `db_client.py` em SQLite + `models.py` + testes reais
- [x] F3 Cache e status de busca em memória (remoção do pacote `redis` fica para a F4)
- [x] F4 `task_runner.py` + APScheduler com recuperação na abertura
- [x] F5 `desktop_app.py` + `main.py`, validado sem Docker
- [x] F6 Playwright via Edge/Chrome do sistema, Firecrawl opcional, script para copiar os dados da web (só leitura; cópia feita), comparativo de navegadores
- [x] F7 Janela nativa (pywebview), PyInstaller `--onedir` sem dados do dev (Sandbox descartado)
- [x] F8 Botões de checagem (detalhes + Atualizar todos), fila com prioridade, workflow de build/release (Windows, rascunho) + `README-EXE.md` (novo, o `README.md` atual fica)
- [x] F9 Aviso de versão nova, tela Sobre/Diagnóstico, grupos no banco (configurações e backup ficaram para depois)
