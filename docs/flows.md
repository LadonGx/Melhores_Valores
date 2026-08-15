# Request Flows — Melhores Valores

## Flow 1: Add Product for Monitoring

```
User → POST /monitor/add { url: "https://amazon.com.br/..." }
  │
  ├─ web_server.py
  │   ├─ Normalize URL (strip #fragment)
  │   ├─ detect_store(url) → "amazon"
  │   ├─ db_client.get_or_create_product(url, store) → product
  │   └─ process_price_check.delay(url) → task queued
  │
  └─ Response: { product_id, store, status: "queued" }

Async (Celery worker):
  process_price_check(url)
  │
  ├─ cache_manager.get(url) → HIT?
  │   └─ HIT: upsert name if better, add_price_history, return
  │
  └─ MISS: scraping_orchestrator.run(url, store)
      ├─ Level 1 (httpx) → adapter → { name, price, image_url } or None
      ├─ Level 2 (Playwright) → adapter → ... or None  [always for MercadoLivre]
      └─ Level 3 (Firecrawl) → adapter → ... or None  [only if L1+L2 failed]
          │
          └─ db_client.get_or_create_product(url, store, name, imageUrl)
             db_client.add_price_history(product_id, price, inStock)
             cache_manager.set(url, { price, name, store }, ttl=7200)
```

## Flow 2: Price Refresh (Synchronous)

```
User → POST /product/{id}/refresh
  │
  └─ web_server.py
      ├─ db_client.get_product_by_id(id) → product
      ├─ run_price_pipeline(product.url, product.store)  ← SYNC, 60s timeout
      │   └─ same cascade as above but blocking
      └─ Response: { ok: true, price } or { ok: false, reason }
```

## Flow 3: Product Search by Name

```
User → POST /search { query: "iPhone 15" }
  │
  └─ web_server.py
      ├─ task_search_products.delay(query) → task queued
      └─ Response: { search_id, status: "queued" }

Async (Celery worker):
  task_search_products(query)
  │
  ├─ search_orchestrator.search(query)
  │   ├─ Tokenize query, filter PT-BR stopwords
  │   ├─ Parallel: search_amazon(query) + search_mercadolivre(query)
  │   ├─ Filter results: token overlap ≥ 50% relevance threshold
  │   └─ Returns List[SearchResult]
  │
  └─ db_client.save_search_results(search_id, query, results)

User → GET /search/{search_id}
  └─ db_client.get_search_results(search_id)
     → List[SearchResult] ordered by price ASC
```

## Flow 4: Scheduled Price Refresh (Every 6h)

```
Celery Beat → schedule_all_products() every 6 hours
  │
  └─ db_client.get_all_products()
     │
     └─ For each product:
         process_price_check.delay(product.url)
         (same as Flow 1, cache will hit if < 2h old)
```

## Flow 5: Frontend Product List

```
React Query useProducts() → GET /products
  │
  └─ db_client.get_all_products()
     └─ For each product: latest PriceHistory entry
     → List[{ product, currentPrice, inStock, scrapedAt }]

Mutations (add/remove/refresh):
  onSuccess → queryClient.invalidateQueries(productKeys.all)
  → triggers refetch of /products
```

## Flow 6: Delete Product

```
User → DELETE /product/{id}
  │
  └─ db_client.delete_product(id)
     └─ Cascade deletes: Product + all PriceHistory entries
```

## Cache Behavior

```
Cache key: SHA256(normalized_url)
Cache value: { price, name, store, url } as JSON
TTL: 7200 seconds (2 hours)

Cache HIT  → skip scraping, write price to DB, return
Cache MISS → run cascade, write to cache on success
```

## Timing Reference

| Operation | Approx. Duration |
|---|---|
| httpx scrape (Level 1) | ~1s |
| Playwright scrape (Level 2) | ~5–8s |
| Firecrawl scrape (Level 3) | ~3–10s (paid) |
| Sync refresh endpoint timeout | 60s |
| Cache TTL | 2 hours |
| Beat schedule interval | 6 hours |
