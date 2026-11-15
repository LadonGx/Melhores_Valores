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

## Browser details (`playwright_scraper.py`)

### User agent
- Never hard-coded. The Chromium version comes from `browser.version`, and the UA is built as a stable **desktop Linux** Chrome: `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/<major>.0.0.0 Safari/537.36` (no "HeadlessChrome"). Linux because the container is Linux; `sec-ch-ua` and `sec-ch-ua-platform` follow the override and agree with it.
- `locale="pt-BR"`, `timezone_id="America/Sao_Paulo"`, `Accept-Language: pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7`, and `navigator.languages` aligned in `_STEALTH_JS`. The init script no longer fakes `webdriver`/`plugins` (the browser already reports `webdriver === false` and 5 real plugins).
- Persistent contexts need the UA *before* they exist, so the version is discovered **once per process** (a throwaway launch, cached in `_browser_version_cache`). Disposable contexts refresh the cache for free.
- If the version cannot be parsed, no UA override is sent (Chromium default) and nothing fails.

### Headless mode: new headless (`channel="chromium"`)
Measured inside the Docker image (Playwright 1.64.1, Chromium 156), with the same UA override:

| | `chromium-headless-shell` (Playwright default) | New headless (`channel="chromium"`) — **chosen** |
|---|---|---|
| Default `navigator.userAgent` | `HeadlessChrome/156.0.8078.4` | `HeadlessChrome/156.0.0.0` |
| `sec-ch-ua` without UA override | includes `"HeadlessChrome";v="156"` | `"Not:A-Brand", "Chromium"` only |
| `navigator.plugins.length` | 0 | 5 |
| Binary | separate shell | full Chromium |

New headless looks like a real Chrome (real plugins, no "HeadlessChrome" brand), so it was chosen. The `Dockerfile` installs only that binary: `playwright install --no-shell chromium`.

### Persistent profile (`profile="mercadolivre"`)
- `fetch_html_playwright(..., profile="mercadolivre")` uses `launch_persistent_context(<BROWSER_PROFILE_DIR>/mercadolivre, ...)` with the same options as the disposable context. `profile=None` (default; Amazon and searches) keeps a disposable context.
- `BROWSER_PROFILE_DIR` defaults to `<repo root>/.browser-profile` (`/app/.browser-profile` in the container) and is read at call time. The profile keeps visitor cookies only — never log in.
- **Warm-up**: empty profile (first run / just recreated) → visit `https://www.mercadolivre.com.br/` and wait ~3 s before the listing. Used profile → straight to the listing.
- **Locks**: exclusivity between processes/containers is the global Redis lock in `store_lock.py` (the caller already holds it). Locally there is also a file lock (`<BROWSER_PROFILE_DIR>/mercadolivre.lock`, `fcntl.flock`, Linux/macOS only — Windows runs without it). Stale `Singleton*` files (Chromium's `SingletonLock/Cookie/Socket`) left by a dead process are removed before opening.
- **Never fails the check because of the profile**: if the profile cannot be opened (corrupted, in use, lock timeout) a warning is logged and the check runs in a disposable context (with the home warm-up).
- **Recreate** = delete the directory (`rm -rf <BROWSER_PROFILE_DIR>/mercadolivre`, or the whole volume). Automatically, a profile above `BROWSER_PROFILE_MAX_MB` (default 300) is deleted and recreated before opening (logged).
- The API and the worker are different containers and must have **different** profile volumes (see root `README.md`).

## What NOT to Change

- Do not parse HTML inside scrapers — pass raw string to adapter
- Do not add store-specific logic here — that belongs in the orchestrator
- Do not share browser instances between tasks (Playwright must be isolated per task)

## Risks

- Playwright increases memory/CPU significantly — do not use it unless needed
- Playwright Chromium must be installed in Docker image (`playwright install --no-shell chromium`)
- httpx may be blocked by anti-bot measures — this is expected, escalate to Level 2
