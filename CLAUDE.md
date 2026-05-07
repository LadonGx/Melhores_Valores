# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Melhores Valores** is a price tracker API for Brazilian e-commerce platforms (Amazon BR, Mercado Livre, AliExpress). It monitors product prices via web scraping and provides product search functionality.

## Monorepo Structure

```
/
├── apps/web/          # React + Vite + TypeScript frontend
├── packages/types/    # Shared TypeScript types (@mv/types)
├── packages/utils/    # Shared utilities (@mv/utils)
├── execution/         # Python backend (FastAPI + Celery)
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

### Docker (primary workflow — backend)
```bash
docker-compose up -d          # Start all services (db, redis, api, worker, beat)
docker-compose logs -f api    # Tail API logs
docker-compose logs -f worker # Tail Celery worker logs
docker-compose down           # Stop all services
```

### Local Python (without Docker)
```bash
pip install -r requirements.txt
uvicorn execution.web_server:app --host 0.0.0.0 --port 8000 --reload
celery -A execution.worker_tasks worker --loglevel=info
celery -A execution.worker_tasks beat --loglevel=info
```

### Database
```bash
prisma generate                            # Regenerate Prisma client after schema changes
prisma migrate dev --name <migration_name> # Apply schema changes
```

## Architecture

The system follows a **3-layer architecture** (documented in `.agents/workflows/arquitetura.md`):

1. **Directives** (`/directives/`) — Business rules as markdown SOPs (caching rules, adapter patterns, scraping strategy, etc.)
2. **Orchestrators** (`execution/*_orchestrator.py`, `execution/worker_tasks.py`) — Decision logic that coordinates execution
3. **Execution** (`execution/`) — Deterministic, focused modules (scrapers, adapters, cache, db)

### Services (docker-compose)
- **db**: PostgreSQL 15 (port 5432)
- **redis**: Redis 7 (port 6379) — cache + Celery broker
- **api**: FastAPI on port 8000
- **worker**: Celery worker (2 concurrent tasks)
- **beat**: Celery Beat — triggers `schedule_all_products()` every 6 hours

### Request Flow: Price Tracking

```
POST /monitor/add {"url": "..."} 
  → detect store → enqueue Celery task
  → Worker: check Redis cache (2h TTL)
  → Cache miss: 3-level scraping cascade:
      1. httpx (fast, free)
      2. Playwright/Chromium (slower, free)
      3. Firecrawl API (paid, last resort)
  → Route to store adapter (amazon/mercadolivre/aliexpress)
  → Save to PostgreSQL via Prisma → update Redis cache
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
| `execution/worker_tasks.py` | Celery app config + all task definitions |
| `execution/db_client.py` | **Only** place DB is accessed — Prisma CRUD operations |
| `execution/scraping_orchestrator.py` | 3-level cascade scraping strategy |
| `execution/search_orchestrator.py` | Multi-store search coordination |
| `execution/cache_manager.py` | Redis get/set with SHA256 URL keys |
| `execution/adapters/` | Store-specific HTML parsers (amazon, mercadolivre, aliexpress) |
| `execution/scrapers/` | HTTP fetching strategies (httpx, Playwright) |
| `execution/search_scrapers/` | Store search page scrapers |
| `schema.prisma` | DB schema: `Product`, `PriceHistory`, `SearchResult` |

## Critical Design Constraints

- **`db_client.py` is the only DB access point** — never call Prisma directly from other modules.
- **Prisma is sync-only** (`interface = "sync"` in schema) — do not use async/await with it.
- **Cache-first**: Always check Redis before scraping; only escalate through the cascade on cache miss.
- **Adapter pattern**: Each store has an isolated adapter — changes in one store's layout only require editing that store's file.
- **Firecrawl is the last resort** — it is a paid API; only use it when httpx and Playwright both fail.

## Environment Variables

Required in `.env`:
```
DATABASE_URL="postgresql://user:password@localhost:5432/price_tracker"
REDIS_URL="redis://localhost:6379/0"
FIRECRAWL_API_KEY="..."
```
