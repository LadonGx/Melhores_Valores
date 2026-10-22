# execution/ — Python Backend

## Objective
Houses the entire Python backend: FastAPI server, Celery workers, database client, scraping engine, and all integrations.

## Responsibilities
- Expose REST API endpoints (FastAPI)
- Run async scraping tasks (Celery)
- Store/retrieve data (SQLite, local file in the user data dir)
- Cache prices (Redis)
- Coordinate multi-level scraping cascade
- Coordinate multi-store product search

## File Map

| File | Role | Modify when |
|---|---|---|
| `web_server.py` | FastAPI routes | Adding/changing API endpoints |
| `worker_tasks.py` | Celery tasks + Beat schedule | Adding async tasks or changing schedule |
| `db_client.py` | **ONLY DB access point** | Adding DB operations |
| `db_schema.py` | SQLite schema + migrations | Changing tables/indexes (append a migration) |
| `models.py` | Pydantic models returned by `db_client` | Adding/removing DB fields |
| `settings.py` | Data dir, DB path, config loading | Adding paths/config |
| `scraping_orchestrator.py` | 3-level cascade logic | Changing scraping strategy |
| `search_orchestrator.py` | Multi-store search | Changing search logic/relevance |
| `cache_manager.py` | Redis get/set | Changing cache behavior |
| `store_detection.py` | URL → store string | Adding new store detection |
| `firecrawl_api.py` | Paid API wrapper | Changing Firecrawl integration |

## Critical Rules

1. **`db_client.py` is the only DB access point.** Never use `sqlite3` elsewhere.
2. **DB access is sync.** One connection per thread, writes via `_write()`. No `async/await`.
3. **Cache-first.** Always check Redis before scraping.
4. **Firecrawl is last resort.** Only call after httpx + Playwright both fail.
5. **Adapters are isolated.** Each store adapter changes independently.

## Subfolders

- `adapters/` — Per-store HTML parsers. See `adapters/README.md`.
- `scrapers/` — HTTP fetch strategies. See `scrapers/README.md`.
- `search_scrapers/` — Search page scrapers. See `search_scrapers/README.md`.

## Environment Dependencies

```
MV_DATA_DIR   → (optional) overrides the user data dir where the SQLite file lives
REDIS_URL     → Redis connection string
FIRECRAWL_API_KEY → Paid API key (Firecrawl)
```

## Internal Dependencies

```
web_server.py
  ├── db_client.py
  ├── worker_tasks.py (via .delay())
  └── store_detection.py

worker_tasks.py
  ├── db_client.py
  ├── scraping_orchestrator.py
  ├── search_orchestrator.py
  └── cache_manager.py

scraping_orchestrator.py
  ├── scrapers/base_scraper.py
  ├── scrapers/playwright_scraper.py
  ├── firecrawl_api.py
  └── adapters/{store}.py

search_orchestrator.py
  └── search_scrapers/{store}_search.py
```

## web_server.py — Endpoint Reference

| Method | Path | Sync/Async | Description |
|---|---|---|---|
| GET | `/products` | Sync | All products with latest prices |
| POST | `/monitor/add` | Async | Add URL, enqueue scraping |
| DELETE | `/product/{id}` | Sync | Remove product + history |
| POST | `/product/{id}/refresh` | Sync (60s) | Force price check |
| PATCH | `/product/{id}/name` | Sync | Update product name |
| GET | `/product/{id}/history` | Sync | Price history + stats |
| POST | `/search` | Async | Search by name, enqueue task |
| GET | `/search/{search_id}` | Sync | Get search results |

## worker_tasks.py — Task Reference

| Task | Trigger | Description |
|---|---|---|
| `process_price_check(url)` | On demand + Beat | Cache check → cascade scrape → DB write |
| `schedule_all_products()` | Every 6 hours (Beat) | Re-queues all monitored products |
| `task_search_products(query)` | On demand | Parallel search → filter → DB write |

## db_client.py — Function Reference

| Function | Description |
|---|---|
| `get_or_create_product(url, store, name?, imageUrl?)` | Upsert product |
| `get_product_by_id(id)` | Fetch single product |
| `update_product_name(id, name)` | Manual name override |
| `add_price_history(product_id, price, inStock)` | Log price entry (deduped: skips insert if price/inStock unchanged since last entry on the same BRT calendar day) |
| `get_price_stats(id)` | current/lowest/average/median price (median = Postgres `percentile_cont(0.5)` semantics) |
| `get_group_price_stats(ids)` | Real pooled lowest/median across multiple products' history |
| `get_latest_price_entry(id)` | Most recent history row for a product |
| `get_price_history_chart(id, days)` | History points within a day window (for charting) |
| `get_price_history_page(id, page, limit)` | Paginated raw history (most recent first) |
| `get_all_products()` | All products with latest price |
| `delete_product(id)` | Cascade delete (`ON DELETE CASCADE`) |
| `save_search_results(search_id, query, results)` | Persist search |
| `get_search_results(search_id)` | Retrieve results by price ASC |

## Risks

- Changing `worker_tasks.py` task function names breaks in-flight Celery tasks.
- Changing `cache_manager.py` key format invalidates all cached prices.
- Changing `db_client.py` function signatures breaks all callers.
- Opening `sqlite3` connections outside `db_client.py` bypasses the write lock and can cause "database is locked".
