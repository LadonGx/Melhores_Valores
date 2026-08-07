# Amazon Adapter
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Block signals by category — ordered from most specific to most generic
_BLOCK_SIGNALS: dict[str, list[str]] = {
    "captcha":      ["captcha", "prove you're not a robot", "enter the characters"],
    "login_wall":   ["sign in to continue", "faça login", "acesse sua conta"],
    "rate_limited": ["rate limited", "429 too many", "too many requests"],
    "challenge_js": ["just a moment", "checking your browser", "cloudflare"],
    "access_denied":["access denied", "403 forbidden", "acesso negado", "forbidden"],
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


def _parse_price_text(text: str) -> float | None:
    """Converts 'R$ 1.299,00' or '1.299,00' to float 1299.0."""
    try:
        cleaned = re.sub(r"[R$\s\xa0]", "", text)
        cleaned = cleaned.replace(".", "").replace(",", ".")
        val = float(cleaned)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _extract_price_from_soup(soup) -> tuple[float | None, str, float]:
    """
    Returns (price, selector_used, confidence_score).
    Never returns crossed-out prices, "was" prices, or installment blocks.
    """
    # Strategy 0: span.priceToPay / apexPriceToPay — explicit "price you pay" class.
    # Amazon uses this for sale prices AND regular prices on modern pages.
    # Must run before Strategy 1 to catch discounted prices correctly.
    for cls in ("span.priceToPay", "span.apexPriceToPay"):
        pay_el = soup.select_one(cls)
        if pay_el:
            offscreen = pay_el.select_one("span.a-offscreen")
            if offscreen:
                val = _parse_price_text(offscreen.get_text(strip=True))
                if val:
                    return val, f"{cls} span.a-offscreen", 0.96

    # Strategy 1: span.a-offscreen inside non-struck, non-"was" span.a-price
    # Skip a-text-strike (strikethrough) AND a-text-price (Amazon's "was price" grey text)
    for price_span in soup.select("span.a-price"):
        classes = price_span.get("class", [])
        if "a-text-strike" in classes or "a-text-price" in classes:
            continue  # skip the "from" / original / "was" price
        offscreen = price_span.select_one("span.a-offscreen")
        if offscreen:
            val = _parse_price_text(offscreen.get_text(strip=True))
            if val:
                return val, "span.a-price:not(.a-text-strike):not(.a-text-price) > span.a-offscreen", 0.92

    # Strategy 2: #corePrice_feature_div — primary product price container
    core = soup.select_one("#corePrice_feature_div")
    if core:
        # Prefer the first non-struck offscreen inside the core price div
        for offscreen in core.select("span.a-offscreen"):
            parent = offscreen.parent
            if parent and "a-text-strike" not in parent.get("class", []):
                val = _parse_price_text(offscreen.get_text(strip=True))
                if val:
                    return val, "#corePrice_feature_div span.a-offscreen", 0.88

    # Strategy 3: legacy price block IDs and deal price (older product pages)
    for price_id in ("#priceblock_dealprice", "#priceblock_ourprice", "#price_inside_buybox"):
        el = soup.select_one(price_id)
        if el:
            val = _parse_price_text(el.get_text(strip=True))
            if val:
                return val, price_id, 0.82

    # Strategy 4: whole + fraction split (more error-prone, lower confidence)
    for price_span in soup.select("span.a-price"):
        if "a-text-strike" in price_span.get("class", []) or "a-text-price" in price_span.get("class", []):
            continue
        whole_el = price_span.select_one("span.a-price-whole")
        if whole_el:
            try:
                whole = re.sub(r"[^\d]", "", whole_el.get_text(strip=True))
                frac_el = price_span.select_one("span.a-price-fraction")
                frac = re.sub(r"[^\d]", "", frac_el.get_text(strip=True)) if frac_el else "00"
                val = float(f"{whole}.{frac or '00'}")
                if val > 0:
                    return val, "span.a-price-whole + span.a-price-fraction", 0.72
            except (ValueError, TypeError):
                pass

    return None, "", 0.0


def _is_out_of_stock(soup) -> bool:
    """Check availability section text; defaults to in-stock if element not found."""
    avail = soup.select_one("#availability span")
    if avail:
        text = avail.get_text(strip=True).lower()
        return any(kw in text for kw in ("fora de estoque", "indisponível", "unavailable", "out of stock"))
    return False


def extract_from_html(html: str) -> dict | None:
    """
    Parses raw HTML from an Amazon product page.
    Returns a dict with price, name, confidence_score, selector_used, block_category.
    Returns None on complete parse failure.
    """
    soup = BeautifulSoup(html, "lxml")

    block_category = _detect_block_category(soup)
    if block_category:
        logger.warning(
            "Amazon | bloqueio detectado | block_category=%s", block_category
        )
        return {
            "price": None, "name": None, "image_url": None,
            "confidence_score": 0.0, "selector_used": "",
            "block_category": block_category,
        }

    try:
        price, selector_used, confidence = _extract_price_from_soup(soup)
        in_stock = not _is_out_of_stock(soup)

        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else None

        image_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
        image_url = (image_el.get("src") or image_el.get("data-src")) if image_el else None

        if price is None:
            if not in_stock:
                # Page explicitly confirms unavailability — propagate so history records it
                logger.info("Amazon | produto fora de estoque sem preço exibido | url implícita")
                return {
                    "name": title,
                    "price": None,
                    "currency": "BRL",
                    "image_url": image_url,
                    "in_stock": False,
                    "selector_used": "",
                    "confidence_score": 0.75,
                    "block_category": None,
                }
            logger.info("Amazon | preço não encontrado em nenhum seletor")
            return None

        logger.debug(
            "Amazon | price=%.2f selector=%s confidence=%.2f in_stock=%s",
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
        logger.exception("Amazon | erro inesperado ao extrair HTML")
        return None
