# apps/web/src/services/ — API Service Layer

## Objective
Single layer for all HTTP communication with the backend. All Axios calls are centralized here.

## Files

| File | Responsibility |
|---|---|
| `api.ts` | Axios singleton instance + interceptors |
| `products.ts` | Product-related API calls |
| `search.ts` | Search-related API calls |

## api.ts — Axios Instance

```typescript
// Singleton — do NOT create new axios instances elsewhere
import api from '@/services/api'
```

- Base URL: `''` (relative — Vite proxy handles routing to `:8000`)
- Error interceptor: normalizes error responses
- No auth headers (no auth system currently)

## products.ts — Function Reference

| Function | Method | Path | Description |
|---|---|---|---|
| `getAll()` | GET | `/products` | All monitored products |
| `add(req)` | POST | `/monitor/add` | Queue URL for monitoring |
| `remove(id)` | DELETE | `/product/{id}` | Remove product |
| `getHistory(id)` | GET | `/product/{id}/history` | Price history |
| `rescrape(url)` | POST | `/monitor/add` | Re-queue existing URL |
| `refreshPrice(id)` | POST | `/product/{id}/refresh` | Sync refresh (60s timeout) |
| `updateName(id, name)` | PATCH | `/product/{id}/name` | Rename product |

## Rules

- **All API calls go through this layer** — no axios/fetch calls in components or pages.
- **Use the `api` singleton** — never `axios.create()` in other files.
- **Return typed responses** — all functions return `Promise<TypeFromPackages>`.
- **Throw on error** — let React Query handle error state.

## Adding a New Service

```typescript
// In the appropriate service file:
import api from './api'
import type { MyResponse } from '@mv/types'

export async function myAction(param: string): Promise<MyResponse> {
  const { data } = await api.post<MyResponse>('/my-endpoint', { param })
  return data
}
```

## What NOT to Do

- Do not import `axios` directly in feature/page/component files.
- Do not duplicate error handling — the interceptor in `api.ts` handles it.
- Do not add business logic here — services are thin HTTP wrappers.

## Risks

- Changing function signatures breaks hooks that call them.
- Adding a new service file requires creating a corresponding hook in `features/`.
