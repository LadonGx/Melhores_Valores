import logging

from .scrapers.base_scraper import fetch_html_simple
from .scrapers.playwright_scraper import fetch_html_playwright
from .firecrawl_api import scrape_product_data
from .store_detection import detect_store_from_url as detect_store
from .adapters import amazon, mercadolivre, aliexpress

logger = logging.getLogger(__name__)

ADAPTERS = {
    "amazon": amazon.extract_from_html,
    "mercadolivre": mercadolivre.extract_from_html,
    "aliexpress": aliexpress.extract_from_html,
}

# Stores that render prices via JavaScript — skip Level 1 (httpx)
JS_REQUIRED_STORES = {"mercadolivre", "aliexpress"}

# Minimum confidence to accept a result and stop the cascade.
# Below this threshold the result is treated as uncertain and the next level is tried.
_CONFIDENCE_ACCEPT = 0.55


def _log_cascade_result(level: int, store: str, result: dict | None, url: str) -> None:
    if result is None:
        logger.info(
            "Cascata nível %d | store=%s | resultado=None (falha de fetch ou parse) | url=%s",
            level, store, url,
        )
        return

    price = result.get("price")
    confidence = result.get("confidence_score", 0.0)
    selector = result.get("selector_used", "")
    block = result.get("block_category")

    if block:
        logger.warning(
            "Cascata nível %d | store=%s | block_category=%s | url=%s",
            level, store, block, url,
        )
    elif price is not None:
        logger.info(
            "Cascata nível %d | store=%s | price=%.2f | confidence=%.2f | selector=%s | url=%s",
            level, store, price, confidence, selector, url,
        )
    else:
        logger.info(
            "Cascata nível %d | store=%s | preço não encontrado | url=%s",
            level, store, url,
        )


def _result_is_acceptable(result: dict | None) -> bool:
    """True if the result has a valid price with sufficient confidence."""
    if not result:
        return False
    if result.get("price") is None:
        return False
    return result.get("confidence_score", 0.0) >= _CONFIDENCE_ACCEPT


def scrape_product(url: str, store: str = None) -> dict | None:
    """
    Orchestrates scraping in cascade:
      Level 1 → httpx simple    (free, ~1s)   — skipped for JS-heavy stores
      Level 2 → Playwright      (free, ~5-8s)
      Level 3 → Firecrawl API   (paid, last resort)

    Each level stops the cascade when it returns a result with confidence >= _CONFIDENCE_ACCEPT.
    Low-confidence results escalate to the next level for a better extraction attempt.
    """
    if not store:
        store = detect_store(url)

    adapter = ADAPTERS.get(store)
    if not adapter:
        logger.warning("Loja não suportada: store=%s | url=%s", store, url)
        return None

    # --- Level 1: httpx simple ---
    if store not in JS_REQUIRED_STORES:
        logger.debug("Cascata nível 1 iniciando | store=%s | url=%s", store, url)
        html = fetch_html_simple(url)
        if html:
            result = adapter(html)
            _log_cascade_result(1, store, result, url)
            if _result_is_acceptable(result):
                return result

    # --- Level 2: Playwright ---
    logger.debug("Cascata nível 2 iniciando | store=%s | url=%s", store, url)
    html = fetch_html_playwright(url)
    if html:
        result = adapter(html)
        _log_cascade_result(2, store, result, url)
        if _result_is_acceptable(result):
            return result

    # --- Level 3: Firecrawl API (paid — last resort) ---
    logger.warning(
        "Cascata nível 3 (Firecrawl) — consumindo crédito | store=%s | url=%s", store, url
    )
    return scrape_product_data(url)
