# packages/utils/ — Shared Utilities (@mv/utils)

## Objective
Shared, pure utility functions used across frontend modules. No React, no API calls.

## File
`src/index.ts` — all utilities exported from this single file.

## Expected Utilities

- Currency formatting (BRL)
- Date formatting (pt-BR locale)
- Price statistics (min, max, average)
- String helpers

## Usage

```typescript
import { formatCurrency, formatDate } from '@mv/utils'

formatCurrency(1299.90)  // → "R$ 1.299,90"
formatDate('2024-01-15T10:00:00Z')  // → "15/01/2024"
```

## Rules

- **Pure functions only** — no side effects, no React hooks.
- **No API calls, no imports from `services/` or `features/`.**
- **Fully typed** — all inputs and outputs typed.

## Adding a New Utility

1. Add function to `src/index.ts`
2. Export from the same file
3. Import via `@mv/utils`

## Risks

- Changing function signatures breaks all callers.
- Adding locale-specific behavior requires testing across environments.
