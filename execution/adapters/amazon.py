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


def extract_in_stock(json_data) -> bool:
    """Reads the 'available' field from Firecrawl's structured extraction. Defaults to True."""
    data = json_data.get("data", json_data)
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    value = metadata.get("available")
    return value if isinstance(value, bool) else True


def _parse_price_text(text: str) -> float | None:
    """Converts 'R$ 1.299,00' or '1.299,00' to float 1299.0."""
    try:
        cleaned = re.sub(r"[R$\s\xa0]", "", text)
        cleaned = cleaned.replace(".", "").replace(",", ".")
        val = float(cleaned)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


# Trusted containers for product price extraction.
# Prices outside these areas (e.g. carousels, sponsored cards, "sims-*" widgets)
# are ignored to avoid false positives.
_PRODUCT_PRICE_CONTAINERS = (
    "#corePrice_feature_div",
    "#corePriceDisplay_desktop_feature_div",
    "#apex_desktop",
    "#apex_desktop_newAccordionRow",
    "#mediaTab_heading_0",
)


# Positive signs that the listing has no main offer (only "see all buying choices").
_NO_MAIN_OFFER_SIGNALS = "#buybox-see-all-buying-choices, #all-offers-display"


def _extract_tmm_selected_price(soup) -> tuple[float, str, float, str] | None:
    """
    Extracts the price from the SELECTED format button in #tmmSwatches.

    Returns (price, selector_used, confidence, offer_type) or None.
    - "a partir de R$X" → offer_type "third_party_from", confidence 0.6
    - Direct price (e.g. Kindle R$84,71) → offer_type "main", confidence 0.78
    """
    tmm = soup.select_one("#tmmSwatches")
    if not tmm:
        return None

    selected = tmm.select_one(".a-button-selected")
    if not selected:
        return None

    slot_price = selected.select_one("span.slot-price")
    if not slot_price:
        return None

    price_text = slot_price.get_text(strip=True)
    if not price_text:
        return None

    is_from_price = "a partir de" in price_text.lower()

    match = re.search(r"R\$[\s\xa0]*(\d[\d.,]*)", price_text.replace("\xa0", " "))
    if not match:
        return None

    val = _parse_price_text(match.group(0))
    if not val:
        return None

    if is_from_price:
        return val, "#tmmSwatches .a-button-selected .slot-price (a partir de)", 0.6, "third_party_from"
    return val, "#tmmSwatches .a-button-selected .slot-price", 0.78, "main"


def _extract_price_from_soup(soup) -> tuple[float | None, str, float, str]:
    """
    Returns (price, selector_used, confidence_score, offer_type).

    Searches ONLY inside trusted product-price containers to avoid picking up
    prices from recommendation carousels, sponsored cards, or "sims-*" widgets.
    offer_type is "main" for the primary offer or "third_party_from" for
    the "a partir de" price of the selected format in #tmmSwatches.
    """
    # Strategy 0: span.priceToPay / apexPriceToPay inside trusted containers.
    for container_sel in _PRODUCT_PRICE_CONTAINERS:
        container = soup.select_one(container_sel)
        if not container:
            continue
        for cls in ("span.priceToPay", "span.apexPriceToPay"):
            pay_el = container.select_one(cls)
            if pay_el:
                offscreen = pay_el.select_one("span.a-offscreen")
                if offscreen:
                    val = _parse_price_text(offscreen.get_text(strip=True))
                    if val:
                        return val, f"{container_sel} {cls} span.a-offscreen", 0.96, "main"

    # Strategy 1: span.a-offscreen inside non-struck, non-"was" span.a-price
    # ONLY inside trusted price containers.
    for container_sel in _PRODUCT_PRICE_CONTAINERS:
        container = soup.select_one(container_sel)
        if not container:
            continue
        for price_span in container.select("span.a-price"):
            classes = price_span.get("class", [])
            if "a-text-strike" in classes or "a-text-price" in classes:
                continue
            offscreen = price_span.select_one("span.a-offscreen")
            if offscreen:
                val = _parse_price_text(offscreen.get_text(strip=True))
                if val:
                    return val, f"{container_sel} span.a-price span.a-offscreen", 0.92, "main"

    # Strategy 2: #corePrice_feature_div fallback — non-struck offscreen
    core = soup.select_one("#corePrice_feature_div")
    if core:
        for offscreen in core.select("span.a-offscreen"):
            parent = offscreen.parent
            if parent and "a-text-strike" not in parent.get("class", []):
                val = _parse_price_text(offscreen.get_text(strip=True))
                if val:
                    return val, "#corePrice_feature_div span.a-offscreen", 0.88, "main"

    # Strategy 3: legacy price block IDs and deal price (older product pages)
    for price_id in ("#priceblock_dealprice", "#priceblock_ourprice", "#price_inside_buybox"):
        el = soup.select_one(price_id)
        if el:
            val = _parse_price_text(el.get_text(strip=True))
            if val:
                return val, price_id, 0.82, "main"

    # Strategy 4: whole + fraction of the visible (highlighted) price ONLY inside trusted containers.
    # This is the price Amazon shows in big type, already with the promotion applied (e.g. the
    # "5% off à vista" Pix/NuPay price), while #tmmSwatches keeps the regular price. The project
    # always records the promotional price, so this runs before the format button.
    for container_sel in _PRODUCT_PRICE_CONTAINERS:
        container = soup.select_one(container_sel)
        if not container:
            continue
        for price_span in container.select("span.a-price"):
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
                        return val, f"{container_sel} span.a-price-whole + span.a-price-fraction", 0.72, "main"
                except (ValueError, TypeError):
                    pass

    # Strategy 5: price of the SELECTED format button in #tmmSwatches (direct price only).
    # Fallback when the page has no visible price block (e.g. Kindle).
    tmm_result = _extract_tmm_selected_price(soup)
    if tmm_result and tmm_result[3] == "main":
        return tmm_result

    # Strategy 6: "a partir de" price of the selected format (no main offer, only other sellers).
    if tmm_result:
        return tmm_result

    return None, "", 0.0, "none"


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
        price, selector_used, confidence, offer_type = _extract_price_from_soup(soup)
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
            if not title or not soup.select_one(_NO_MAIN_OFFER_SIGNALS):
                # No positive sign that the listing lacks a main offer (the price block may just
                # be missing from this HTML): let the cascade escalate, as before
                logger.info("Amazon | preço não encontrado em nenhum seletor")
                return None
            # Product page read successfully, Amazon only offers "see all buying choices"
            # and there is no "a partir de" price: no main offer
            logger.info("Amazon | sem oferta principal | offer_type=none")
            return {
                "name": title,
                "price": None,
                "currency": "BRL",
                "image_url": image_url,
                "in_stock": True,
                "selector_used": "",
                "confidence_score": 0.6,
                "block_category": None,
                "offer_type": "none",
            }

        logger.debug(
            "Amazon | price=%.2f selector=%s confidence=%.2f in_stock=%s offer_type=%s",
            price, selector_used, confidence, in_stock, offer_type,
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
            "offer_type": offer_type,
        }
    except Exception:
        logger.exception("Amazon | erro inesperado ao extrair HTML")
        return None
