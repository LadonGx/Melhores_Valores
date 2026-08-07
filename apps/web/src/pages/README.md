# apps/web/src/pages/ — Route-Level Components

## Objective
Top-level components that map 1:1 to application routes. Pages compose features and layout, not business logic.

## Pages

| Folder | Route | Description |
|---|---|---|
| `Dashboard/` | `/` | Overview stats and quick actions |
| `Products/` | `/products` | Monitored products table (main page) |
| `History/` | `/history` | Price history charts |
| `Search/` | `/search` | Product search by name |
| `Settings/` | `/settings` | Application settings |

## Rules

- **No business logic in pages.** Pages only compose hooks and feature components.
- **No direct API calls.** Use hooks from `features/*/hooks/`.
- **No useState for server data.** Use React Query via feature hooks.
- **No inline styles.** Use `<Page>.module.css`.

## Products/index.tsx — Reference (most complex page)

Key patterns used:
- `useProducts()` for product list
- `useRemoveProduct()`, `useRefreshPrice()`, `useUpdateProductName()` for mutations
- Per-row loading state via `Set<string>` (refreshingIds)
- Inline name editing: click pencil → input → Enter/Escape
- Modal for AddProductForm and SearchByName
- Toast notifications on mutation success/error
- Store badge with per-store color styling
- Currency format: `Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`
- Date format: `toLocaleDateString('pt-BR')`

## Adding a New Page

1. Create `pages/NewPage/index.tsx` and `pages/NewPage/NewPage.module.css`
2. Add route in `app/router.tsx`
3. Add nav link in `components/Sidebar/`
4. Create feature hook if needed in `features/<domain>/hooks/`

## What NOT to Do

- Do not move reusable UI from pages to `components/` unless it's truly reusable.
- Do not skip the CSS Module — every page has its own `.module.css`.
- Do not hardcode data — always fetch via hooks.

## Risks

- Pages depend on feature hooks — changing hook return shape requires updating page.
- Removing a route without removing Sidebar link leaves dead navigation.
