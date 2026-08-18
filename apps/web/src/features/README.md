# apps/web/src/features/ — Domain Feature Modules

## Objective
Encapsulate all domain-specific logic per feature: React Query hooks, mutations, and feature-specific components that are too coupled to a domain to live in `components/`.

## Structure

```
features/
  products/
    components/          ← Components only used by Products feature
      AddProductForm.tsx
      ProductDetailModal.tsx
    hooks/
      useProducts.ts     ← All React Query hooks for products
      useProductGroups.ts
  search/
    components/
      SearchByName.tsx
    hooks/
      useSearch.ts
```

## Rules

- **Hooks own server state** — all `useQuery` / `useMutation` calls live here, never in pages.
- **Feature components are domain-coupled** — if a component is only used by one domain, it lives here.
- **Reusable UI primitives go to `components/`** — not here.
- **Pages import from features** — features never import from pages.

## products/hooks/useProducts.ts — Hook Reference

| Hook | Query Key | Description |
|---|---|---|
| `useProducts()` | `productKeys.all` | All products, stale: 2min |
| `useProductHistorySummary(id, range)` | `productKeys.historySummary(id, range)` | Stats + chart series for a product |
| `useProductHistoryTable(id, limit)` | `productKeys.historyTable(id, limit)` | Paginated raw history (infinite query, "carregar mais") |
| `useGroupPriceStats(ids)` | `productKeys.groupStats(ids)` | Real pooled lowest/median across a group's listings |
| `useAddProduct()` | mutation | Add URL, 5s delay before invalidate |
| `useRemoveProduct()` | mutation | Delete product |
| `useRescrapeProduct()` | mutation | Re-queue scraping, 8s delay |
| `useRefreshPrice()` | mutation | Sync refresh (60s timeout) |
| `useUpdateProductName()` | mutation | Rename product |

## Invalidation Pattern

All mutations invalidate `productKeys.all` on success:
```typescript
onSuccess: () => {
  queryClient.invalidateQueries({ queryKey: productKeys.all })
}
```

Delays (5s for add, 8s for rescrape) account for async backend processing time before the new data appears.

## What NOT to Do

- Do not call `services/` directly from page components — go through feature hooks.
- Do not put reusable UI (Button, Card) in features — those belong in `components/`.
- Do not share hooks between unrelated features — keep domains isolated.

## Risks

- Removing a hook invalidates pages that depend on it — check usages before deleting.
- Changing query keys breaks cache coherence between hooks.
