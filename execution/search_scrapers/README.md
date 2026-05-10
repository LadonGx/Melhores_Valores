# execution/search_scrapers/ — Store Search Scrapers

## Objective
Scrape search result pages (query → list of products) from each store. Different from product scrapers which handle single product pages.

## Responsibilities
- Accept a search query string
- Fetch and parse the store's search results page
- Return a list of product result dicts

## Files

| File | Store | Status |
|---|---|---|
| `amazon_search.py` | Amazon BR | Active |
| `mercadolivre_search.py` | Mercado Livre | Active |

**Disabled stores:** Magazine Luiza, Shopee (blocked from datacenter IPs — do not re-enable without residential proxy).

## Interface Contract

```python
def search(query: str) -> list[dict]:
    """
    Returns list of:
    {
        "title": str,
        "price": float,
        "currency": str,         # "BRL"
        "image_url": str | None,
        "product_url": str,
        "rating": float | None,
        "review_count": int | None,
        "store": str             # "amazon" | "mercadolivre"
    }
    Returns [] on failure (never raises).
    """
```

## Who Calls Search Scrapers

Only `search_orchestrator.py`. Parallel execution via Python threading or asyncio.

```python
from execution.search_scrapers import amazon_search, mercadolivre_search

results = amazon_search.search(query)
results = mercadolivre_search.search(query)
```

## Relevance Filtering

Relevance filtering (token overlap ≥ 50%) is done in `search_orchestrator.py`, not here. Return all results from the search page; the orchestrator filters.

## What NOT to Change

- Do not add relevance logic to scrapers — it belongs in the orchestrator
- Do not call `db_client` from here — orchestrator handles persistence
- Do not re-enable Shopee/Magalu without residential proxy setup

## Risks

- Search page HTML structure changes break scrapers (return [])
- Rate limiting from stores — scrapers should handle gracefully (return [])
- New search scrapers require registration in `search_orchestrator.py`
