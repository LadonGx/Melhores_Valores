# Architecture — Melhores Valores

## High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React + Vite, port 3000)                              │
│  React Query ←→ services/ ←→ Axios → proxy /api/* → :8000      │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼────────────────────────────────────┐
│  FastAPI  (port 8000)      web_server.py                        │
│  Routes: /products  /monitor/add  /product/:id  /search         │
└─────┬───────────────────────────────────────┬───────────────────┘
      │ sync DB calls                          │ enqueue task
      ▼                                        ▼
┌─────────────┐                     ┌──────────────────────┐
│  db_client  │ ←─── Prisma ──────► │  PostgreSQL 15       │
│  (sync)     │                     │  Products            │
└─────────────┘                     │  PriceHistory        │
                                    │  SearchResult        │
                                    └──────────────────────┘
      ▲
      │ DB writes from workers
┌─────┴───────────────────────────────────────────────────────────┐
│  Celery Worker   worker_tasks.py                                 │
│  task: process_price_check()                                     │
│  task: task_search_products()                                    │
│  beat: schedule_all_products() every 6h                         │
└─────┬──────────────────────────┬────────────────────────────────┘
      │                          │
      ▼                          ▼
┌───────────────┐    ┌───────────────────────────────────────────┐
│  Redis 7      │    │  scraping_orchestrator.py                 │
│  - Task queue │    │  Level 1: httpx (fast, free)              │
│  - Price cache│    │  Level 2: Playwright (JS, free)           │
│    (2h TTL)   │    │  Level 3: Firecrawl (paid, last resort)   │
└───────────────┘    └──────────┬────────────────────────────────┘
                                │ raw HTML
                     ┌──────────▼────────────────────────────────┐
                     │  adapters/                                 │
                     │  amazon.py  mercadolivre.py  aliexpress.py│
                     │  → { name, price, image_url }             │
                     └────────────────────────────────────────────┘
```

## Layer Responsibilities

### 1. FastAPI (web_server.py)
- Validates incoming requests
- Normalizes URLs (strips fragments)
- Calls `db_client` for sync reads
- Enqueues Celery tasks for async work
- Never scrapes directly

### 2. Celery Workers (worker_tasks.py)
- `process_price_check`: cache check → scrape cascade → save to DB
- `task_search_products`: parallel search → relevance filter → save to DB
- `schedule_all_products`: Beat-triggered every 6h, re-queues all monitored products
- All workers write to DB exclusively via `db_client`

### 3. db_client.py
- Sole DB access point — all other modules call its functions
- Uses Prisma Python sync client
- Encapsulates garbage-name detection
- Manages Prisma connection lifecycle

### 4. Scraping Cascade (scraping_orchestrator.py)
- Tries Level 1 (httpx) → adapter → validate
- If None or garbage: tries Level 2 (Playwright) → adapter → validate
- If still None: tries Level 3 (Firecrawl) → adapter → validate
- JS-required stores (mercadolivre, aliexpress) skip Level 1

### 5. Adapters (execution/adapters/)
- Input: raw HTML string + store string
- Output: `dict | None` with keys `name`, `price`, `image_url`
- Stateless, deterministic, isolated per store

### 6. React Frontend (apps/web/)
- All server state via React Query (auto-refetch, cache, mutations)
- Local UI state via Zustand (modals, loading states)
- API calls only through `services/` layer
- No business logic in pages or components

## Data Models

```
Product
  id          UUID PK
  url         String UNIQUE
  name        String
  imageUrl    String?
  store       String
  createdAt   DateTime
  updatedAt   DateTime
  history     PriceHistory[]

PriceHistory
  id          UUID PK
  price       Float?        (null = out of stock)
  inStock     Boolean
  scrapedAt   DateTime
  productId   String FK → Product

SearchResult
  id          UUID PK
  search_id   String        (groups results per query run)
  query       String
  store       String
  title       String
  price       Float
  currency    String
  image_url   String?
  product_url String
  rating      Float?
  review_count Int?
  found_at    DateTime
  INDEX: (search_id), (query, store)
```

## Port Map

| Service | Port |
|---|---|
| Frontend dev server | 3000 |
| FastAPI | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |

## Deployment

All services via `docker-compose up -d`. No Kubernetes. No cloud deployment configured.
Frontend proxies `/api/*` to `localhost:8000` via Vite config.
