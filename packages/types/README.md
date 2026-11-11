# packages/types/ — Shared TypeScript Types (@mv/types)

## Objective
Single source of truth for all TypeScript interfaces and types shared between frontend modules. No runtime code.

## File
`src/index.ts` — all types exported from this single file.

## Type Reference

### Domain Types
```typescript
type Store = 'amazon' | 'mercadolivre' | string

interface Product {
  id: string
  url: string
  name: string
  imageUrl?: string
  store: Store
  createdAt: string
  updatedAt: string
  currentPrice?: number | null
  inStock?: boolean
  scrapedAt?: string
  // Última verificação (GET /products):
  // last_checked = última checagem BEM-SUCEDIDA; last_attempt_at = última
  // tentativa de qualquer resultado. A tentativa FALHOU quando
  // last_check_status é 'error'/'blocked' e (last_checked é nulo OU
  // last_attempt_at > last_checked).
  last_checked?: string | null
  last_attempt_at?: string | null
  last_check_status?: LastCheckStatus | null
  last_check_error?: string | null   // motivo: login_wall, captcha, access_denied, rate_limited, challenge_js, scrape_failed, invalid_price, price_rejected, exception
}

type LastCheckStatus = 'ok' | 'out_of_stock' | 'no_offer' | 'error' | 'blocked'

interface PriceHistoryEntry {
  id: string
  price: number | null   // null = out of stock
  inStock: boolean
  scrapedAt: string
}

interface ProductWithHistory extends Product {
  history: PriceHistoryEntry[]
  lowestPrice?: number | null
  averagePrice?: number | null
}

interface SearchResult {
  id: string
  search_id: string
  query: string
  store: Store
  title: string
  price: number
  currency: string
  image_url?: string
  product_url: string
  rating?: number
  review_count?: number
  found_at: string
}
```

### API Response Types
```typescript
interface HealthResponse { status: string }
interface AddProductResponse { product_id: string; store: Store; status: string }
interface SearchResponse { search_id: string; status: string }
interface SearchResultsResponse { results: SearchResult[]; count: number }
interface RefreshPriceResponse
  | { ok: true; price: number | null; inStock: boolean }
  | { ok: false; reason: string }

type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed'

interface ProductGroup {
  store: Store
  products: Product[]
}
```

## Rules

- **All shared types go here** — never define types inline in service or hook files.
- **No runtime code** — this package is types only (no functions, no classes).
- **Import as `@mv/types`** — configured in tsconfig path aliases.

## Usage

```typescript
import type { Product, SearchResult, RefreshPriceResponse } from '@mv/types'
```

## Adding New Types

1. Add to `src/index.ts`
2. Export from the same file
3. Import in any frontend module via `@mv/types`

## Risks

- Removing or renaming a type breaks all importers — search for usages first.
- Types must stay in sync with Python dicts in `execution/db_client.py` — update both.
- Adding required fields to existing interfaces is a breaking change for all callers.
