# AGENTS.md — AI Navigation & Development Context

> **Primary reference for AI assistants.** Read this before generating or modifying any code.
> For deeper context, follow the AI Navigation links at the bottom.

---

## System Overview

**Melhores Valores** is a Brazilian e-commerce price tracker. It monitors product prices via web scraping (Amazon BR, Mercado Livre, AliExpress) and exposes a REST API + React dashboard.

**Core loop:** User submits URL → scraper runs cascade → price saved → dashboard updates.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Query v5, React Router v6, Zustand, Axios, CSS Modules |
| Backend | Python 3.11+, FastAPI, Celery, Prisma (sync), PostgreSQL 15, Redis 7 |
| Scraping | httpx, Playwright/Chromium, Firecrawl API |
| Infra | Docker Compose (db, redis, api, worker, beat) |
| Monorepo | pnpm workspaces: `apps/web`, `packages/types`, `packages/utils` |

---

## Architecture

3-layer model:

```
Directives (/directives/)        ← Business rules (markdown SOPs)
     ↓
Orchestrators (execution/)       ← Decision logic & coordination
     ↓
Execution (execution/)           ← Deterministic modules (scrapers, adapters, cache, db)
```

**Backend module map:**

```
execution/
  web_server.py          ← FastAPI routes (port 8000)
  worker_tasks.py        ← Celery tasks + Beat schedule
  db_client.py           ← ONLY DB access point (Prisma sync)
  scraping_orchestrator.py ← 3-level cascade logic
  search_orchestrator.py ← Multi-store search with relevance filter
  cache_manager.py       ← Redis SHA256-keyed cache (2h TTL)
  store_detection.py     ← URL → store string classifier
  firecrawl_api.py       ← Paid API wrapper (last resort)
  adapters/              ← Per-store HTML parsers
  scrapers/              ← HTTP fetch strategies
  search_scrapers/       ← Per-store search page scrapers
```

**Frontend module map:**

```
apps/web/src/
  app/                   ← Providers (QueryClient + Router)
  pages/                 ← Route-level components
  features/              ← Domain logic (hooks + feature components)
  components/            ← Reusable UI primitives
  services/              ← Axios API calls
  store/                 ← Zustand global state
  styles/                ← Global CSS
```

---

## Critical Design Constraints

1. **`db_client.py` is the ONLY DB access point.** Never import or call Prisma from any other module.
2. **Prisma is sync-only** (`interface = "sync"`). Never use `async/await` with Prisma calls.
3. **Cache-first strategy.** Always check Redis before scraping. Never bypass the cache.
4. **Firecrawl is last resort** (paid API). Only called when httpx + Playwright both fail.
5. **Adapter isolation.** Each store adapter is independent — changes in one never touch another.
6. **JS-required stores skip Level 1.** `mercadolivre` and `aliexpress` skip httpx and go straight to Playwright.
7. **Garbage name detection** is in `db_client.py`. Never duplicate this logic elsewhere.
8. **Frontend types** live exclusively in `packages/types/src/index.ts`. No inline type duplication.

---

## Code Conventions

### Python (execution/)
- Functions are synchronous unless it's a Celery task (`@app.task`)
- All DB calls go through functions in `db_client.py`
- Scraping functions return `dict | None`
- Adapters receive raw HTML string, return `{"name": str, "price": float | None, "image_url": str | None}`
- Store names are lowercase strings: `"amazon"`, `"mercadolivre"`, `"aliexpress"`
- Logging via standard `logging` module; tasks use Celery logger
- No print statements in production code

### TypeScript (apps/web/)
- All shared interfaces in `@mv/types` (packages/types)
- CSS Modules only — no inline styles, no Tailwind
- React Query for all server state; Zustand only for local UI state
- Hooks in `features/<domain>/hooks/` — never in pages or components
- Services in `services/` — no fetch/axios calls outside this folder
- Components are functional with named exports
- File naming: `PascalCase` for components, `camelCase` for hooks/services/utils

### Naming
- Python: `snake_case` for functions/vars, `PascalCase` for classes
- TypeScript: `camelCase` for vars/functions, `PascalCase` for types/components
- CSS class names: camelCase in CSS Modules
- Celery task names: `task_<action>_<resource>` (e.g., `task_search_products`)
- React Query keys: defined as objects in hooks (e.g., `productKeys.all`)

---

## Development Rules

1. **No business logic in pages.** Pages compose features and handle layout only.
2. **No direct API calls in components.** All API calls go through `services/`.
3. **No Prisma outside `db_client.py`.**
4. **No Firecrawl calls outside `firecrawl_api.py`.**
5. **Mutations invalidate React Query cache** — always call `queryClient.invalidateQueries` on success.
6. **Celery tasks are idempotent** — re-running a task must not corrupt data.
7. **Cache TTL is 2 hours** — do not hardcode different values elsewhere.
8. **Product URLs are normalized** (fragment stripped) before storage or cache lookup.
9. **Prices are stored as floats** in DB; displayed as BRL currency in UI.
10. **Search results are ordered by price ASC** — do not change this default.

---

## Common Mistakes to Avoid

- **DO NOT** call `prisma.product.find_many()` outside `db_client.py`.
- **DO NOT** add `async def` to db_client functions — Prisma is sync.
- **DO NOT** create new Axios instances — use the singleton from `services/api.ts`.
- **DO NOT** fetch data in page components — use hooks from `features/`.
- **DO NOT** use `mercadolivre` in Level 1 (httpx) scraping — it requires JS rendering.
- **DO NOT** call Firecrawl unless both httpx and Playwright returned None/garbage.
- **DO NOT** add new shared types anywhere except `packages/types/src/index.ts`.
- **DO NOT** add inline styles — use CSS Modules.
- **DO NOT** store product URL with `#fragment` — normalize before use.
- **DO NOT** use `console.log` in production TS code.
- **DO NOT** duplicate garbage-name detection logic — it lives only in `db_client.py`.

---

## Safe Refactor Rules

These changes are **safe** without broader review:
- Adding new fields to `packages/types/src/index.ts` (non-breaking additions)
- Adding new CSS rules to existing `.module.css` files
- Adding new Celery tasks that don't touch DB schema
- Adding new adapter functions in existing adapter files
- Adding new React Query hooks in `features/*/hooks/`

These changes **require explicit confirmation**:
- Modifying `schema.prisma` (requires migration)
- Changing `db_client.py` function signatures
- Changing `worker_tasks.py` task names (breaks in-flight tasks)
- Modifying `cache_manager.py` key format (invalidates all cached data)
- Changing CORS origins in `web_server.py`
- Upgrading major dependencies

These folders/files are **never modified without explicit user instruction**:
- `.env` (secrets)
- `docker-compose.yml`
- `schema.prisma` (without migration plan)
- `pnpm-workspace.yaml`

---

## Checklist Before Generating Code

- [ ] Did I read the README.md for the target folder?
- [ ] Am I modifying the correct layer (execution vs web vs packages)?
- [ ] If touching DB: am I going through `db_client.py`?
- [ ] If adding types: am I adding to `packages/types/src/index.ts`?
- [ ] If adding API call in frontend: am I using `services/`?
- [ ] If adding server state: am I using React Query (not Zustand)?
- [ ] Does this change require a Prisma migration?
- [ ] Does this change break existing Celery task names?

---

## AI Navigation

| Task | Read first |
|---|---|
| Add/modify scraping | `execution/README.md` → `execution/scrapers/README.md` |
| Add/modify store adapter | `execution/adapters/README.md` |
| Add/modify search | `execution/search_scrapers/README.md` |
| Add/modify DB operations | `execution/README.md` (db_client section) |
| Add/modify API endpoint | `execution/README.md` (web_server section) |
| Add/modify frontend page | `apps/web/src/pages/README.md` |
| Add/modify feature logic | `apps/web/src/features/README.md` |
| Add/modify UI component | `apps/web/src/components/README.md` |
| Add/modify API service | `apps/web/src/services/README.md` |
| Add/modify shared types | `packages/types/README.md` |
| Understand full flows | `docs/flows.md` |
| Understand architecture | `docs/architecture.md` |
| Understand conventions | `docs/conventions.md` |
| Understand stack details | `docs/stack.md` |
