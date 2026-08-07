# Conventions — Melhores Valores

## Python Conventions (execution/)

### Function Signatures
```python
# Scraper: returns dict or None
def scrape_product(url: str) -> dict | None: ...

# Adapter: receives HTML, returns parsed data or None
def parse_product(html: str) -> dict | None:
    # returns {"name": str, "price": float | None, "image_url": str | None}

# DB client: all functions are synchronous
def get_product_by_id(product_id: str) -> dict | None: ...

# Celery task: decorated, always return value or raise
@app.task(bind=True)
def process_price_check(self, url: str) -> dict: ...
```

### Error Handling
- Scrapers return `None` on failure (never raise to caller)
- Adapters return `None` if price/name can't be parsed
- DB functions may raise — callers handle exceptions
- Celery tasks log exceptions and return error dict, never re-raise

### Logging
```python
import logging
logger = logging.getLogger(__name__)
# In tasks, use task logger:
self.update_state(state='PROGRESS', meta={...})
```

### Store Strings
Always lowercase. Valid values: `"amazon"`, `"mercadolivre"`, `"aliexpress"`.
Never use display names (e.g., `"Amazon BR"`) in code — only in UI.

### Garbage Name Detection
Defined in `db_client.py`. Names containing these are garbage (do not save):
- `"rate limit"`, `"access denied"`, `"captcha"`, `"cloudflare"`
- Portuguese equivalents: `"acesso negado"`, `"verificação"`, etc.

## TypeScript Conventions (apps/web/)

### File Naming
```
PascalCase   → React components, type files
camelCase    → hooks, services, utilities, CSS class names
kebab-case   → NOT used (CSS Modules use camelCase)
```

### Imports Order
1. React
2. Third-party libraries
3. `@mv/*` workspace packages
4. Local absolute (`@/`)
5. Relative (`./`, `../`)

### React Query Keys
```typescript
// Defined as objects in hook files, not strings
const productKeys = {
  all: ['products'] as const,
  detail: (id: string) => ['products', id] as const,
}
```

### Mutation Pattern
```typescript
const mutation = useMutation({
  mutationFn: service.action,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: productKeys.all })
    toast.success('Done')
  },
  onError: (err) => toast.error(err.message),
})
```

### CSS Modules
```tsx
import styles from './Component.module.css'
// Usage:
<div className={styles.container}>
// Multiple classes:
<div className={`${styles.base} ${styles.active}`}>
```

### Environment Variables (Frontend)
- Must be prefixed `VITE_`
- Accessed via `import.meta.env.VITE_API_URL`
- Default API URL resolved by Vite proxy — do not hardcode `localhost:8000`

## API Contract

### Request Format
All POST bodies are JSON. Content-Type: `application/json`.

### Response Format (Backend → Frontend)
```typescript
// Success responses match types in packages/types/src/index.ts
// Errors follow FastAPI default: { detail: string }
```

### Date Format
- Backend stores UTC timestamps
- Frontend formats for display using `toLocaleDateString('pt-BR')`
- Never store formatted dates — always raw ISO strings from API

### Currency
- Backend: `Float` (e.g., `1299.90`)
- Frontend display: `new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`
- Never store formatted currency strings

## Git Conventions

### Branch Names
```
feat/<description>     → new feature
fix/<description>      → bug fix
refactor/<description> → code improvement without feature change
docs/<description>     → documentation only
```

### Commit Messages
```
feat: add AliExpress search scraper
fix: handle null price in ProductCard
refactor: extract price formatting to @mv/utils
```

## Environment Variables

Required in root `.env`:
```
DATABASE_URL="postgresql://user:password@localhost:5432/price_tracker"
REDIS_URL="redis://localhost:6379/0"
FIRECRAWL_API_KEY="fc-..."
```

Optional in `apps/web/.env`:
```
VITE_API_URL=http://localhost:8000   (usually not needed — Vite proxy handles it)
```
