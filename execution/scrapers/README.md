# execution/scrapers/ — HTTP Fetch Strategies

## Objective
Fetch raw HTML from product pages using different strategies. Each scraper represents one level of the cascade: fast/free → slower/free → paid.

## Responsibilities
- Fetch raw HTML string from a given URL
- Return `None` on failure (network error, timeout, block)
- Never parse HTML — that is the adapter's job

## Files

| File | Level | Strategy | Speed | Cost |
|---|---|---|---|---|
| `base_scraper.py` | Level 1 | httpx (plain HTTP) | ~1s | Free |
| `playwright_scraper.py` | Level 2 | Playwright/Chromium | ~5–8s | Free |

Level 3 (Firecrawl) is NOT in this folder — it lives in `execution/firecrawl_api.py`.

## Interface Contract

```python
def fetch(url: str) -> str | None:
    """
    Returns raw HTML string, or None on failure.
    Never raises to the caller.
    """
```

## Who Calls Scrapers

Only `scraping_orchestrator.py`. The orchestrator decides which scraper to use based on store and previous failure.

```python
from execution.scrapers import base_scraper, playwright_scraper

html = base_scraper.fetch(url)         # Level 1
html = playwright_scraper.fetch(url)   # Level 2
```

## Level Selection Rules (enforced by orchestrator)

- `mercadolivre`: **skip Level 1**, always start at Level 2 (require JS)
- `amazon`: start at Level 1, escalate to Level 2 on failure
- Any store: escalate to Level 3 (Firecrawl) only when Level 1 AND Level 2 both return None

## What NOT to Change

- Do not parse HTML inside scrapers — pass raw string to adapter
- Do not add store-specific logic here — that belongs in the orchestrator
- Do not share browser instances between tasks (Playwright must be isolated per task)

## Risks

- Playwright increases memory/CPU significantly — do not use it unless needed
- Playwright Chromium must be installed in Docker image (`playwright install chromium`)
- httpx may be blocked by anti-bot measures — this is expected, escalate to Level 2
