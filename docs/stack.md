# Stack Reference — Melhores Valores

## Backend

### FastAPI
- Version: latest stable
- Usage: REST API, request validation via Pydantic, CORS middleware
- Entry: `execution/web_server.py`
- Run: `uvicorn execution.web_server:app --host 127.0.0.1 --port 8000 --reload`
- `lifespan` starts the scheduler and stops scheduler + task pool on shutdown

### Background tasks (`task_runner.py`) — replaces Celery worker
- Two `ThreadPoolExecutor` queues, 2 workers each: `user` (default) and `background` (batch checks)
- `@task` / `@task(bind=True)` decorator: `.delay()` returns `TaskHandle(id, future)`; `self.request.id` equals the handle id
- Failures are logged with the task id; queued tasks are dropped when the app closes

### Scheduler (`scheduler.py`, APScheduler 3.11) — replaces Celery Beat
- `BackgroundScheduler` (UTC): `run_full_check` → `schedule_all_products()` every 6h
- Anchored to `AppMeta.last_full_check`: next run = last + 6h, or 1 min after start if overdue
- `max_instances=1`, `coalesce=True`, `misfire_grace_time=None`

### SQLite
- Driver: `sqlite3` (Python stdlib), sync
- File: `<user data dir>/melhores_valores.db` (`MV_DATA_DIR` / `MV_DB_PATH` override) — see `execution/settings.py`
- Schema + migrations: `execution/db_schema.py`, versioned by `PRAGMA user_version`, applied on first connection
- Mode: WAL, foreign keys on; one connection per thread, writes serialized by a lock
- Models: Pydantic, `execution/models.py`  
- Access: only through `db_client.py`

### httpx
- Sync HTTP client for Level 1 scraping
- Handles redirects, custom User-Agent headers
- Returns raw HTML string or raises

### Playwright (Python) 1.64.0
- Browser automation for Level 2 scraping (and the Amazon search fallback), using the system Edge/Chrome (`playwright_scraper._BROWSER_CANDIDATES`); Playwright's own Chromium is the last resort
- 1.44 was too old for current Edge (intermittent launch failures) — keep Playwright reasonably recent
- Used for JS-heavy pages (all MercadoLivre)
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

## Runtime

No Docker, Redis or Celery: API, background tasks, scheduler, cache and SQLite all run in one Python process.

- Entry: `python main.py` → `execution/launcher.py`
- Root app `execution/desktop_app.py`: `/api` → `web_server.app`, `/` → `apps/web/dist` (SPA fallback, `index.html` with `Cache-Control: no-cache`)
- Port: 47290 by default, then the last used port (`<data dir>/port`); `--port` overrides. Must stay stable: `localStorage` is per origin
- Single instance via `<data dir>/app.lock` + `GET /api/` health check
- Logs: `<data dir>/logs/app.log` (rotating, 1 MB × 3)
