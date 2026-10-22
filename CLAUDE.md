# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Melhores Valores** is a price tracker API for Brazilian e-commerce platforms (Amazon BR, Mercado Livre). It monitors product prices via web scraping and provides product search functionality.

## Monorepo Structure

```
/
├── apps/web/          # React + Vite + TypeScript frontend
├── packages/types/    # Shared TypeScript types (@mv/types)
├── packages/utils/    # Shared utilities (@mv/utils)
├── execution/         # Python backend (FastAPI, SQLite, background threads)
├── pnpm-workspace.yaml
└── package.json       # Workspace root
```

## Development Commands

### Frontend (pnpm)
```bash
# Install all workspace dependencies (run from repo root)
pnpm install

# Start frontend dev server (port 3000)
pnpm dev

# Build frontend
pnpm build
```

### Backend (single process — no Docker, Redis or Celery)
```bash
pip install -r requirements.txt
uvicorn execution.web_server:app --host 127.0.0.1 --port 8000 --reload
```
One process runs everything: the API, background tasks (`task_runner`, 2 threads) and the 6h scheduler (`scheduler`, started by the `lifespan` in `web_server.py`).

### Database
SQLite file created automatically on first access, in the user data dir
(`%LOCALAPPDATA%\MelhoresValores\melhores_valores.db` on Windows; override with `MV_DATA_DIR`).
Schema changes: append a new entry to `MIGRATIONS` in `execution/db_schema.py` (versioned by `PRAGMA user_version`).

> Branch `exe` is migrating to a single-process desktop app — see `docs/plano-executavel.md`.
> Done: SQLite (Phase 2), in-memory cache (Phase 3), threads + APScheduler (Phase 4). Still pending: single entry point serving the frontend (Phase 5), packaging.

## Architecture

The system follows a **3-layer architecture** (documented in `.agents/workflows/arquitetura.md`):

1. **Directives** (`/directives/`) — Business rules as markdown SOPs (caching rules, adapter patterns, scraping strategy, etc.)
2. **Orchestrators** (`execution/*_orchestrator.py`, `execution/worker_tasks.py`) — Decision logic that coordinates execution
3. **Execution** (`execution/`) — Deterministic, focused modules (scrapers, adapters, cache, db)

### Runtime (one process)
- **API**: FastAPI (`web_server.py`), bound to `127.0.0.1`
- **Background tasks**: `task_runner.py` — thread pool (2 workers) with a Celery-like `@task` / `.delay()` / `self.request.id` interface
- **Scheduler**: `scheduler.py` — APScheduler runs `schedule_all_products()` every 6h, anchored to the last full check stored in `AppMeta` (catch-up 1 min after start if overdue)
- **Cache**: in-memory `memory_cache` (`cache_manager.py`)
- **DB**: SQLite file in the user data dir

### Request Flow: Price Tracking

```
POST /monitor/add {"url": "..."} 
  → detect store → enqueue background task (task_runner)
  → Worker: check in-memory cache (2h TTL)
  → Cache miss: 3-level scraping cascade:
      1. httpx (fast, free)
      2. Playwright/Chromium (slower, free)
      3. Firecrawl API (paid, last resort)
  → Route to store adapter (amazon/mercadolivre)
  → Save to SQLite via db_client → update in-memory cache
```

### Request Flow: Product Search

```
POST /search {"query": "iPhone 15"}
  → enqueue task_search_products()
  → Search Orchestrator: parallel search across Amazon + Mercado Livre
  → Aggregate results → save to SearchResult table
  → return search_id

GET /search/{search_id} → retrieve results ordered by price ASC
```

## Key Files

| File | Purpose |
|------|---------|
| `execution/web_server.py` | FastAPI app — 4 endpoints (health, monitor, history, search) |
| `execution/worker_tasks.py` | Price pipeline + all task definitions (`@task`) |
| `execution/task_runner.py` | Thread-pool task queue (replaces Celery worker) |
| `execution/scheduler.py` | APScheduler 6h full check + catch-up (replaces Celery Beat) |
| `execution/db_client.py` | **Only** place DB is accessed — SQLite (`sqlite3`) CRUD operations |
| `execution/db_schema.py` | DB schema + migrations: `Product`, `PriceHistory`, `SearchResult` |
| `execution/models.py` | Pydantic models returned by `db_client` (same field names the Prisma models had) |
| `execution/settings.py` | User data dir, DB path, `.env`/`config.env` loading |
| `execution/scraping_orchestrator.py` | 3-level cascade scraping strategy |
| `execution/search_orchestrator.py` | Multi-store search coordination |
| `execution/cache_manager.py` | In-memory TTL cache (`memory_cache`, thread-safe) with SHA256 URL keys — replaces Redis |
| `execution/adapters/` | Store-specific HTML parsers (amazon, mercadolivre) |
| `execution/scrapers/` | HTTP fetching strategies (httpx, Playwright) |
| `execution/search_scrapers/` | Store search page scrapers |

## Critical Design Constraints

- **`db_client.py` is the only DB access point** — never touch `sqlite3` / the DB file from other modules.
- **DB access is sync** — one connection per thread; writes go through `_write()` (lock + transaction). Do not use async/await with it.
- **Dates are stored as ISO 8601 UTC text** (`db_client._iso`) — keep that single format so text ordering/comparison stays correct.
- **Cache-first**: Always check the cache (`cache_manager`) before scraping; only escalate through the cascade on cache miss. The cache is per-process and lost on exit (it is only an optimization).
- **Adapter pattern**: Each store has an isolated adapter — changes in one store's layout only require editing that store's file.
- **Firecrawl is the last resort** — it is a paid API; only use it when httpx and Playwright both fail.

## Environment Variables

In `.env` (repo, dev) or `config.env` (user data dir):
```
FIRECRAWL_API_KEY="..."   # optional — without it, cascade level 3 is skipped
MV_DATA_DIR="./.data"     # optional — overrides the user data dir
```
