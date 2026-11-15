import logging
import time
from typing import NamedTuple

from .scrapers.base_scraper import fetch_html_simple
from .scrapers.playwright_scraper import fetch_html_playwright
from .firecrawl_api import scrape_product_data
from .store_detection import detect_store_from_url as detect_store
from .adapters import amazon, mercadolivre
from .store_health import record_failure, record_ok
from .store_lock import StoreBusyError, store_check_lock  # noqa: F401 — StoreBusyError é reexportado

logger = logging.getLogger(__name__)

ADAPTERS = {
    "amazon": amazon.extract_from_html,
    "mercadolivre": mercadolivre.extract_from_html,
}

# Stores that render prices via JavaScript — skip Level 1 (httpx)
JS_REQUIRED_STORES = {"mercadolivre"}

# Perfil persistente do navegador usado no nível 2 (A2: playwright_scraper). Só o Mercado Livre
# usa; quem chama já está dentro da trava global da loja (store_lock).
BROWSER_PROFILES = {"mercadolivre": "mercadolivre"}

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
    """True if the result has a valid price, or explicitly confirms out-of-stock / no offer."""
    if not result:
        return False
    # Confirmed out-of-stock: stop the cascade so we don't burn Firecrawl credits
    if result.get("in_stock") is False and result.get("confidence_score", 0.0) >= _CONFIDENCE_ACCEPT:
        return True
    # Page read correctly but the listing has no offer (only other sellers, no price shown):
    # escalating to a paid level would see the same page
    if result.get("offer_type") == "none" and result.get("confidence_score", 0.0) >= _CONFIDENCE_ACCEPT:
        return True
    if result.get("price") is None:
        return False
    return result.get("confidence_score", 0.0) >= _CONFIDENCE_ACCEPT


# Block categories where Firecrawl escalation is pointless.
# login_wall / access_denied require authentication that Firecrawl cannot provide.
_NO_FIRECRAWL_BLOCKS = {"login_wall", "access_denied"}


class ScrapeOutcome(NamedTuple):
    """Resultado de uma checagem: dado extraído, bloqueio e nível da cascata."""

    result: dict | None
    block_category: str | None
    # Nível que deu o resultado (1 httpx, 2 Playwright, 3 Firecrawl); em falha, o último nível
    # tentado; None quando nenhum nível rodou (loja não suportada).
    level: int | None
    # Tempo da cascata em ms, medido já dentro da trava (a espera pela trava não conta).
    duration_ms: int | None = None


def scrape_product_with_meta(
    url: str, store: str = None, *, lock_wait_s: float | None = None
) -> ScrapeOutcome:
    """
    Cascata de scraping (ver _scrape_cascade) + registro da saúde da loja (canal "monitor").

    Para lojas com trava global (Mercado Livre) a cascata inteira roda dentro da trava, de modo
    que nunca haja 2 checagens da loja ao mesmo tempo (worker × worker, worker × API).

    Args:
        lock_wait_s: espera máxima pela trava (None → padrão de store_lock).

    Raises:
        StoreBusyError: a trava continuou ocupada durante `lock_wait_s`. Nenhuma checagem
            aconteceu: a saúde da loja NÃO é gravada.
    """
    if not store:
        store = detect_store(url)

    with store_check_lock(store, lock_wait_s):
        started = time.monotonic()
        result, block_category, level = _scrape_cascade(url, store)
        duration_ms = int((time.monotonic() - started) * 1000)

    if result:
        record_ok(store, "monitor")
    else:
        record_failure(store, "monitor", block_category)
    return ScrapeOutcome(result, block_category, level, duration_ms)


def scrape_product_with_block(
    url: str, store: str = None, *, lock_wait_s: float | None = None
) -> tuple[dict | None, str | None]:
    """
    Como scrape_product_with_meta, sem o nível da cascata.

    Returns:
        (resultado, categoria de bloqueio): a categoria só vem preenchida quando a cascata
        falhou (resultado None) e um adapter identificou o bloqueio.
    """
    outcome = scrape_product_with_meta(url, store, lock_wait_s=lock_wait_s)
    return outcome.result, outcome.block_category


def scrape_product(url: str, store: str = None) -> dict | None:
    """Como scrape_product_with_block, mas devolve só o resultado."""
    return scrape_product_with_block(url, store)[0]


def _scrape_cascade(url: str, store: str) -> tuple[dict | None, str | None, int | None]:
    """
    Orchestrates scraping in cascade:
      Level 1 → httpx simple    (free, ~1s)   — skipped for JS-heavy stores
      Level 2 → Playwright      (free, ~5-8s)
      Level 3 → Firecrawl API   (paid, last resort)

    Each level stops the cascade when it returns a result with confidence >= _CONFIDENCE_ACCEPT.
    Returns (resultado, categoria de bloqueio, nível que deu o resultado ou o último tentado).
    Low-confidence results escalate to the next level for a better extraction attempt.
    Firecrawl is skipped when Level 2 confirms a login_wall or access_denied block
    (authentication blocks cannot be resolved by a different scraping service).
    """
    adapter = ADAPTERS.get(store)
    if not adapter:
        logger.warning("Loja não suportada: store=%s | url=%s", store, url)
        return None, None, None

    # --- Level 1: httpx simple ---
    if store not in JS_REQUIRED_STORES:
        logger.debug("Cascata nível 1 iniciando | store=%s | url=%s", store, url)
        html = fetch_html_simple(url)
        if html:
            result = adapter(html)
            _log_cascade_result(1, store, result, url)
            if _result_is_acceptable(result):
                return result, None, 1

    # --- Level 2: Playwright ---
    logger.debug("Cascata nível 2 iniciando | store=%s | url=%s", store, url)
    seen_block: str | None = None
    profile = BROWSER_PROFILES.get(store)
    html = fetch_html_playwright(url, profile=profile) if profile else fetch_html_playwright(url)
    if html:
        result = adapter(html)
        seen_block = result.get("block_category") if result else None
        _log_cascade_result(2, store, result, url)
        if _result_is_acceptable(result):
            return result, None, 2
        # Authentication blocks cannot be solved by Firecrawl — skip to save credits
        if result and result.get("block_category") in _NO_FIRECRAWL_BLOCKS:
            logger.warning(
                "Bloqueio '%s' no nível 2 — Firecrawl não ajudaria, cancelando | store=%s | url=%s",
                result["block_category"], store, url,
            )
            return None, result["block_category"], 2

    # --- Level 3: Firecrawl API (paid — last resort) ---
    logger.warning(
        "Cascata nível 3 (Firecrawl) — consumindo crédito | store=%s | url=%s", store, url
    )
    firecrawl_result = scrape_product_data(url)
    return firecrawl_result, (None if firecrawl_result else seen_block), 3
