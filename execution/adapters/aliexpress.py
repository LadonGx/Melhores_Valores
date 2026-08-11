# AliExpress Adapter
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BLOCK_SIGNALS: dict[str, list[str]] = {
    "login_wall":   ["sign in", "log in", "faça login", "acesse sua conta"],
    "captcha":      ["captcha", "prove you're not a robot", "verify you are human"],
    "challenge_js": ["just a moment", "cloudflare", "checking your browser"],
    "access_denied":["access denied", "forbidden", "acesso negado"],
    "rate_limited": ["too many requests", "rate limited", "429"],
}


def _detect_block_category(soup) -> str | None:
    """Returns block category if the page is an anti-bot/auth wall, else None."""
    combined = ""
    if soup.title:
        combined += soup.title.get_text(strip=True).lower() + " "
    combined += soup.get_text()[:800].lower()
    for category, signals in _BLOCK_SIGNALS.items():
        if any(s in combined for s in signals):
            return category
    return None


def extract_price(json_data):
    data = json_data.get("data", json_data)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    for key in ("price", "product_price", "current_price"):
        value = metadata.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def extract_name(json_data):
    data = json_data.get("data", json_data)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    return metadata.get("title") or metadata.get("name")


def extract_in_stock(json_data) -> bool:
    """Reads the 'available' field from Firecrawl's structured extraction. Defaults to True."""
    data = json_data.get("data", json_data)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    value = metadata.get("available")
    return value if isinstance(value, bool) else True


def _parse_price_text(text: str) -> float | None:
    """Safely converts price text like 'R$ 1.299,00' or 'US $12.99' to float."""
    try:
        # Remove currency symbols and noise
        cleaned = re.sub(r"[R$US\s\xa0]", "", text)
        # Handle both Brazilian (1.299,00) and US (12.99) formats
        if "," in cleaned and "." in cleaned:
            # "1.299,00" → remove thousand sep, swap decimal
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # "1299,00" → swap decimal
            cleaned = cleaned.replace(",", ".")
        val = float(cleaned)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _extract_price_from_soup(soup) -> tuple[float | None, str, float]:
    """
    Returns (price, selector_used, confidence_score).
    Targets the current purchase price, not installment or promotional price.
    """
    # Strategy 1: currentPriceText — the active buy-box price
    el = soup.select_one("[class*='currentPriceText']")
    if el:
        val = _parse_price_text(el.get_text(strip=True))
        if val:
            return val, "[class*='currentPriceText']", 0.82

    # Strategy 2: product-price-value — product page price
    el = soup.select_one("[class*='product-price-value']")
    if el:
        val = _parse_price_text(el.get_text(strip=True))
        if val:
            return val, "[class*='product-price-value']", 0.75

    # Strategy 3: uniform price container (newer page layout)
    el = soup.select_one("[class*='uniform-banner-box-price']")
    if el:
        val = _parse_price_text(el.get_text(strip=True))
        if val:
            return val, "[class*='uniform-banner-box-price']", 0.68

    return None, "", 0.0


_OUT_OF_STOCK_SIGNALS = (
    "this item is no longer available",
    "item unavailable",
    "product unavailable",
    "sold out",
    "esgotado",
    "indisponível",
    "not available",
)


def _is_out_of_stock(soup) -> bool:
    """Returns True if the AliExpress page explicitly indicates the product is unavailable."""
    text = soup.get_text(strip=True).lower()[:1000]
    return any(kw in text for kw in _OUT_OF_STOCK_SIGNALS)


def extract_from_html(html: str) -> dict | None:
    """
    Parses raw HTML from an AliExpress product page.
    Returns a dict with price, name, confidence_score, selector_used, block_category.
    Returns None on complete parse failure.
    """
    soup = BeautifulSoup(html, "lxml")

    block_category = _detect_block_category(soup)
    if block_category:
        logger.warning(
            "AliExpress | bloqueio detectado | block_category=%s", block_category
        )
        return {
            "price": None, "name": None, "image_url": None,
            "confidence_score": 0.0, "selector_used": "",
            "block_category": block_category,
        }

    try:
        title_el = soup.select_one("h1[data-pl='product-title']") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else None

        price, selector_used, confidence = _extract_price_from_soup(soup)
        in_stock = not _is_out_of_stock(soup)

        if price is None:
            if not in_stock:
                logger.info("AliExpress | produto fora de estoque sem preço exibido")
                return {
                    "name": title,
                    "price": None,
                    "currency": "BRL",
                    "image_url": None,
                    "in_stock": False,
                    "selector_used": "",
                    "confidence_score": 0.75,
                    "block_category": None,
                }
            logger.info("AliExpress | preço não encontrado em nenhum seletor")
            return None

        img_el = (
            soup.select_one("[class*='magnifier--image']")
            or soup.select_one(".magnifier-image")
        )
        image_url = img_el.get("src") if img_el else None

        logger.debug(
            "AliExpress | price=%.2f selector=%s confidence=%.2f in_stock=%s",
            price, selector_used, confidence, in_stock,
        )

        return {
            "name": title,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
            "in_stock": in_stock,
            "selector_used": selector_used,
            "confidence_score": confidence,
            "block_category": None,
        }
    except Exception:
        logger.exception("AliExpress | erro inesperado ao extrair HTML")
        return None
