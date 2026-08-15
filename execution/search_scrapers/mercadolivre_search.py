import logging
import re

from bs4 import BeautifulSoup

from ..adapters.mercadolivre import detect_block_category
from ..scrapers.playwright_scraper import fetch_html_playwright
from .errors import StoreBlockedError

# Página de listagem/busca do ML — nunca tem os seletores de página de produto
# que fetch_html_playwright espera por padrão, então usamos os nossos próprios.
_SEARCH_WAIT_SELECTORS = ("li.ui-search-layout__item", "span.andes-money-amount")
_WARMUP_URL = "https://www.mercadolivre.com.br/"

logger = logging.getLogger(__name__)


def _parse_ml_price(item) -> float | None:
    """
    Extrai o preço do card do Mercado Livre.
    O ML usa um único span 'andes-money-amount' com o valor completo (ex: 'R$107,58').
    O seletor de 'integer' separado não funciona em todos os layouts.
    """
    # Tentativa 1: span.andes-money-amount com aria-label (mais confiável)
    amount_el = item.select_one("span.andes-money-amount[aria-label]")
    if amount_el:
        try:
            label = amount_el.get("aria-label", "")  # ex: "107 reais con 58 centavos"
            # Extrai números do aria-label
            nums = re.findall(r"\d+", label)
            if len(nums) >= 2:
                return float(f"{nums[0]}.{nums[1].zfill(2)}")
            elif len(nums) == 1:
                return float(nums[0])
        except Exception:
            pass

    # Tentativa 2: pegar o texto completo do span de preço principal
    # e parsear o formato "R$107,58" ou "107,58"
    price_spans = item.select("span.andes-money-amount")
    for span in price_spans:
        try:
            texto = span.get_text(strip=True)
            # Remove símbolo de moeda e espaços não-quebráveis
            texto = re.sub(r"[R$\s\xa0]", "", texto)
            # Formato BR: 1.234,56 → 1234.56
            texto = texto.replace(".", "").replace(",", ".")
            val = float(texto)
            if val > 0:
                return val
        except Exception:
            continue

    # Tentativa 3: seletores clássicos separados
    price_int  = item.select_one("span.andes-money-amount__integer")
    price_frac = item.select_one("span.andes-money-amount__fraction")
    if price_int:
        try:
            whole = re.sub(r"[^\d]", "", price_int.get_text(strip=True))
            frac  = re.sub(r"[^\d]", "", price_frac.get_text(strip=True)) if price_frac else "00"
            return float(f"{whole}.{frac or '00'}")
        except Exception:
            pass

    return None


def search_mercadolivre(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos no Mercado Livre BR usando Playwright (renderização completa).
    O ML bloqueia httpx com uma página de anti-bot em JavaScript — Playwright
    executa o JS e obtém os resultados reais.

    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    # Remove caracteres especiais e normaliza para o formato esperado pelo ML
    clean = re.sub(r"[^\w\s]", "", query.lower()).strip()
    clean = re.sub(r"\s+", "-", clean)
    url = f"https://lista.mercadolivre.com.br/{clean}"

    html = fetch_html_playwright(
        url,
        wait_ms=3000,
        wait_for_selectors=_SEARCH_WAIT_SELECTORS,
        warmup_url=_WARMUP_URL,
    )
    if not html:
        logger.warning("mercadolivre_search | Playwright sem HTML | query='%s'", query)
        return []

    results = []
    soup  = BeautifulSoup(html, "lxml")
    items = soup.select("li.ui-search-layout__item")

    if not items:
        block_category = detect_block_category(soup)
        if block_category:
            logger.warning(
                "mercadolivre_search | bloqueado (%s) | query='%s'",
                block_category, query,
            )
            raise StoreBlockedError(block_category)

    for item in items[:max_results]:
        try:
            link_el    = item.select_one("a.poly-component__title")
            image_el   = item.select_one("img.poly-component__picture")
            rating_el  = item.select_one("span.poly-reviews__rating")
            reviews_el = item.select_one("span.poly-reviews__total")

            if not link_el:
                continue

            price = _parse_ml_price(item)

            rating = None
            if rating_el:
                try:
                    rating = float(rating_el.get_text(strip=True).replace(",", "."))
                except Exception:
                    pass

            reviews = None
            if reviews_el:
                try:
                    reviews = int(
                        re.sub(r"[^\d]", "", reviews_el.get_text(strip=True))
                    )
                except Exception:
                    pass

            img_src = None
            if image_el:
                img_src = (
                    image_el.get("data-src")
                    or image_el.get("src")
                )
                # Ignora placeholders (base64 ou tiny svg)
                if img_src and (img_src.startswith("data:") or len(img_src) < 20):
                    img_src = None

            results.append({
                "store":        "mercadolivre",
                "title":        link_el.get_text(strip=True),
                "product_url":  link_el.get("href", ""),
                "price":        price,
                "currency":     "BRL",
                "image_url":    img_src,
                "rating":       rating,
                "review_count": reviews,
            })
        except Exception:
            continue

    logger.info("mercadolivre_search | %d resultados | query='%s'", len(results), query)
    return results
