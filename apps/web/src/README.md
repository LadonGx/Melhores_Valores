# apps/web/src/ — React Frontend Source

## Objective
React 18 + TypeScript frontend for the Melhores Valores price tracker dashboard.

## Folder Map

| Folder | Role | When to edit |
|---|---|---|
| `app/` | Providers, router setup | Adding global providers or routes |
| `pages/` | Route-level components | Adding new pages |
| `features/` | Domain logic (hooks + feature components) | Adding domain behavior |
| `components/` | Reusable UI primitives | Adding shared UI |
| `services/` | Axios API layer | Adding/changing API calls |
| `store/` | Zustand global UI state | Adding persistent UI state |
| `styles/` | Global CSS | Global style overrides |

## Architecture Rules

1. **Pages compose features** — no business logic in pages.
2. **Features expose hooks** — data fetching lives in `features/*/hooks/`.
3. **Services are the only API layer** — no fetch/axios outside `services/`.
4. **All shared types in `@mv/types`** — no inline type duplication.
5. **CSS Modules only** — no inline styles, no Tailwind.
6. **React Query for server state** — Zustand only for UI state.

## Data Flow

```
Page
  └─ Feature Hook (useProducts, useSearch, ...)
      └─ React Query (useQuery / useMutation)
          └─ Service (services/products.ts)
              └─ Axios (services/api.ts)
                  └─ FastAPI backend (port 8000)
```

## Routing (app/router.tsx)

| Path | Page | Notes |
|---|---|---|
| `/` | Dashboard | Overview stats |
| `/products` | Products | Main monitoring table |
| `/history` | History | Price history charts |
| `/search` | Search | Search by product name |
| `/settings` | Settings | App configuration |

All routes wrapped in `DashboardLayout` (sidebar + header).

## State Boundaries

| State Type | Tool | Location |
|---|---|---|
| Server data (products, history, search) | React Query | `features/*/hooks/` |
| UI state (modal open, sidebar) | Zustand | `store/app.store.ts` |
| Form state | React Hook Form | Inside feature components |
| Component state | useState | Inside component |

## Environment

- Dev server: port 3000
- API proxy: Vite proxies `/api/*` to `localhost:8000`
- Env vars: `VITE_*` prefix required
