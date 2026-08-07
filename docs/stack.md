# Stack Reference — Melhores Valores

## Backend

### FastAPI
- Version: latest stable
- Usage: REST API, request validation via Pydantic, CORS middleware
- Entry: `execution/web_server.py`
- Run: `uvicorn execution.web_server:app --host 0.0.0.0 --port 8000 --reload`

### Celery
- Broker: Redis (`REDIS_URL`)
- Backend: Redis (task results)
- Workers: 2 concurrent (`--concurrency=2`)
- Beat: `schedule_all_products()` every 6h (crontab)
- Entry: `execution/worker_tasks.py` (`app = Celery(...)`)
- Run: `celery -A execution.worker_tasks worker --loglevel=info`

### Prisma (Python)
- Client: `prisma` Python package (sync interface)
- Schema: `schema.prisma` at repo root
- Generator: `prisma-client-py`
- Interface: `sync` — all calls are blocking
- Connection: managed by `db_client.py`, auto-connected on first call
- Migrations: `prisma migrate dev --name <name>`
- Client regen: `prisma generate`

### PostgreSQL 15
- Port: 5432 (Docker)
- Database: `price_tracker`
- Access: only through `db_client.py`

### Redis 7
- Port: 6379 (Docker)
- Usage 1: Celery broker + results backend
- Usage 2: Price cache (SHA256 keys, 2h TTL)
- Client: `redis-py` (sync) in `cache_manager.py`

### httpx
- Sync HTTP client for Level 1 scraping
- Handles redirects, custom User-Agent headers
- Returns raw HTML string or raises

### Playwright (Python)
- Chromium-based browser automation for Level 2 scraping
- Used for JS-heavy pages (all MercadoLivre, AliExpress)
- Runs in headless mode

### Firecrawl API
- External paid scraping API
- Used only as Level 3 fallback
- Key: `FIRECRAWL_API_KEY` env var
- Client: `execution/firecrawl_api.py`

---

## Frontend

### React 18
- Strict mode enabled
- Functional components only
- Entry: `apps/web/src/main.tsx`

### TypeScript
- Target: ES2020
- Strict mode enabled
- Path aliases: `@/` → `src/`, `@mv/*` → workspace packages

### Vite
- Port: 3000 (dev server)
- Proxy: `/api/*` → `http://localhost:8000`
- Build: ESNext, tree-shaken

### React Query v5 (TanStack Query)
- All server state management
- Default stale time: set per query (products: 2min)
- DevTools: available in dev mode
- QueryClient: created in `app/providers.tsx`

### React Router v6
- Routes defined in `app/router.tsx`
- Layout: `DashboardLayout` wraps all authenticated pages
- No auth currently (planned)

### Zustand
- Used for: local UI state (modal open/close, sidebar)
- Store: `store/app.store.ts`
- Not for server state — that's React Query

### Axios
- Singleton: `services/api.ts`
- Base URL: `''` (relative, proxied by Vite)
- Interceptors: error normalization
- Custom timeout per request (refresh: 60s, search poll: default)

### CSS Modules
- One `.module.css` file per component
- No global class names in component files
- Global styles: `styles/global.css`

### Zod
- Schema validation for form inputs
- Used with React Hook Form

### React Hook Form
- Used in form components (AddProductForm, etc.)
- Validation via Zod resolver

---

## Monorepo (pnpm workspaces)

### packages/types
- Package name: `@mv/types`
- Contains: all shared TypeScript interfaces and types
- No runtime code — types only
- Imported by frontend; mirrored by Python dicts

### packages/utils
- Package name: `@mv/utils`
- Contains: shared formatting utilities (currency, dates)
- Imported by frontend components

### workspace root
- `pnpm install` installs all workspace deps
- `pnpm dev` starts frontend dev server
- `pnpm build` builds frontend for production

---

## Docker Services

| Service | Image | Port | Role |
|---|---|---|---|
| db | postgres:15 | 5432 | Primary database |
| redis | redis:7 | 6379 | Cache + message broker |
| api | custom (Dockerfile) | 8000 | FastAPI REST server |
| worker | custom | — | Celery async worker |
| beat | custom | — | Celery scheduled tasks |
