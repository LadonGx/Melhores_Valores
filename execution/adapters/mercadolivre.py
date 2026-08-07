# Mercado Livre Adapter
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BLOCK_SIGNALS: dict[str, list[str]] = {
    "login_wall":   ["acesse sua conta", "faça seu login", "faça login", "sign in"],
    "captcha":      ["captcha", "prove you're not a robot"],
    "rate_limited": ["rate limited", "too many requests", "429"],
    "challenge_js": ["just a moment", "cloudflare", "checking your browser"],
    "access_denied":["acesso negado", "bloqueado", "access denied", "forbidden"],
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


def _parse_price_from_soup(soup) -> tuple[float | None, str, float]:
    """
    Returns (price, selector_used, confidence_score).
    Targets the purchase price only — not installments, comparatives, or freight.
    """
    # Strategy 1: itemprop="price" meta tag — schema.org standard, highest reliability
    meta = soup.find("meta", {"itemprop": "price"})
    if meta and meta.get("content"):
        try:
            val = float(str(meta["content"]).replace(",", "."))
            if val > 0:
                return val, 'meta[itemprop="price"]', 0.95
        except (ValueError, TypeError):
            pass

    # Strategy 2: .ui-pdp-price__second-line — main purchase price block
    main_block = soup.select_one(".ui-pdp-price__second-line")
    if main_block:
        # 2a: aria-label (e.g. "30 reais com 99 centavos")
        amount_el = main_block.select_one("span.andes-money-amount[aria-label]")
        if amount_el:
            try:
                label = amount_el.get("aria-label", "")
                nums = re.findall(r"\d+", label)
                if len(nums) >= 2:
                    return float(f"{nums[0]}.{nums[1].zfill(2)}"), ".ui-pdp-price__second-line [aria-label]", 0.90
                elif len(nums) == 1:
                    return float(nums[0]), ".ui-pdp-price__second-line [aria-label]", 0.88
            except (ValueError, TypeError):
                pass

        # 2b: fraction + cents elements inside the correct price block
        frac_el = main_block.select_one(".andes-money-amount__fraction")
        if frac_el:
            try:
                whole = re.sub(r"[^\d]", "", frac_el.get_text(strip=True))
                cents_el = main_block.select_one(".andes-money-amount__cents")
                cents = re.sub(r"[^\d]", "", cents_el.get_text(strip=True)) if cents_el else "00"
                val = float(f"{whole}.{cents or '00'}")
                if val > 0:
                    return val, ".ui-pdp-price__second-line .andes-money-amount__fraction", 0.85
            except (ValueError, TypeError):
                pass

    # Strategy 3: .ui-pdp-price__main-container — catalog/variant pages (/p/)
    main_container = soup.select_one(".ui-pdp-price__main-container")
    if main_container:
        amount_el = main_container.select_one("span.andes-money-amount[aria-label]")
        if amount_el:
            try:
                label = amount_el.get("aria-label", "")
                nums = re.findall(r"\d+", label)
                if len(nums) >= 2:
                    return float(f"{nums[0]}.{nums[1].zfill(2)}"), ".ui-pdp-price__main-container [aria-label]", 0.80
                elif len(nums) == 1:
                    return float(nums[0]), ".ui-pdp-price__main-container [aria-label]", 0.78
            except (ValueError, TypeError):
                pass

    return None, "", 0.0


def _is_out_of_stock(soup) -> bool:
    """Returns True if the MercadoLivre page explicitly indicates unavailability."""
    if soup.select_one(".ui-pdp-buybox--unavailable, .ui-pdp-container--unavailable"):
        return True
    stock_el = soup.select_one(".ui-pdp-stock-information, .ui-pdp-buybox__quantity")
    if stock_el:
        text = stock_el.get_text(strip=True).lower()
        if any(kw in text for kw in ("sem estoque", "indisponível", "sem unidades")):
            return True
    return False


def extract_from_html(html: str) -> dict | None:
    """
    Parses raw HTML from a Mercado Livre product page.
    Returns a dict with price, name, confidence_score, selector_used, block_category.
    Returns None on complete parse failure.
    """
    soup = BeautifulSoup(html, "lxml")

    block_category = _detect_block_category(soup)
    if block_category:
        logger.warning(
            "MercadoLivre | bloqueio detectado | block_category=%s", block_category
        )
        return {
            "price": None, "name": None, "image_url": None,
            "confidence_score": 0.0, "selector_used": "",
            "block_category": block_category,
        }

    try:
        title_el = (
            soup.select_one(".ui-pdp-title")
            or soup.select_one("h1.ui-pdp-title")
            or soup.select_one("h1")
        )
        title = title_el.get_text(strip=True) if title_el else None

        price, selector_used, confidence = _parse_price_from_soup(soup)
        in_stock = not _is_out_of_stock(soup)

        if price is None:
            if not in_stock:
                logger.info("MercadoLivre | produto fora de estoque sem preço exibido")
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
            logger.info("MercadoLivre | preço não encontrado com seletores específicos")
            return None

        img_el = (
            soup.select_one(".ui-pdp-gallery__figure__image")
            or soup.select_one("figure.ui-pdp-gallery__figure img")
        )
        image_url = (img_el.get("src") or img_el.get("data-zoom")) if img_el else None

        logger.debug(
            "MercadoLivre | price=%.2f selector=%s confidence=%.2f in_stock=%s",
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
        logger.exception("MercadoLivre | erro inesperado ao extrair HTML")
        return None
