# execution/adapters/ — Store HTML Parsers

## Objective
Parse raw HTML from each e-commerce store into a normalized product dict. Each adapter is fully isolated — one file per store.

## Responsibilities
- Extract `name`, `price`, `image_url` from raw HTML
- Return `None` on parse failure (never raise to caller)
- Handle store-specific HTML structure variations

## Files

| File | Store | Notes |
|---|---|---|
| `amazon.py` | Amazon BR | Handles JS-rendered and static HTML variants |
| `mercadolivre.py` | Mercado Livre | Always receives Playwright-rendered HTML |

## Interface Contract

Every adapter exposes a single public function:

```python
def parse_product(html: str) -> dict | None:
    """
    Returns:
        {
            "name": str,
            "price": float | None,   # None if out of stock
            "image_url": str | None
        }
    or None if parsing fails entirely.
    """
```

## Who Calls Adapters

Only `scraping_orchestrator.py`. Never call adapters directly from tasks or web_server.

```python
# In scraping_orchestrator.py:
from execution.adapters import amazon, mercadolivre

result = amazon.parse_product(html)
```

## Conventions

- CSS selectors or BeautifulSoup — no assumptions about JS state (html is already rendered by caller)
- `price` is always a Python `float`, never a formatted string
- `name` is stripped of whitespace
- Return `None` for the whole dict if the page is a CAPTCHA/block page or structure is unrecognizable
- Do NOT check for garbage names here — `db_client.py` handles that

## What NOT to Change Without Confirmation

- Do not change the return dict keys (`name`, `price`, `image_url`) — used throughout the system
- Do not add network calls — adapters are pure HTML parsers
- Do not import `db_client` or `cache_manager`

## Risks

- Store HTML structure changes break parsers silently (returns None)
- Adding a new key to the return dict requires updating callers
- Duplicate adapters for the same store create confusion — one file per store, always

## Adding a New Store Adapter

1. Create `execution/adapters/<store>.py`
2. Implement `parse_product(html: str) -> dict | None`
3. Add store detection in `execution/store_detection.py`
4. Add scraping logic in `execution/scraping_orchestrator.py`
5. Update `packages/types/src/index.ts` `Store` type
