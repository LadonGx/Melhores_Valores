import logging
import random
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate, br",
    },
]


def _parse_amazon_price(item) -> float | None:
    """
    Extrai o preço do card da Amazon via a-offscreen (método mais confiável).
    O span.a-offscreen contém o preço formatado completo, ex: "R$ 76,15".
    """
    # Método preferido: a-offscreen tem o preço completo formatado
    offscreen = item.select_one("span.a-price > span.a-offscreen")
    if offscreen:
        try:
            texto = offscreen.get_text(strip=True)
            # Remove símbolo de moeda e espaços não-quebráveis
            texto = re.sub(r"[R$\s\xa0]", "", texto)
            # Formato BR: 1.234,56 → 1234.56
            texto = texto.replace(".", "").replace(",", ".")
            val = float(texto)
            if val > 0:
                return val
        except Exception:
            pass

    # Fallback: seletores clássicos separados
    price_whole = item.select_one("span.a-price-whole")
    price_frac  = item.select_one("span.a-price-fraction")
    if price_whole:
        try:
            whole = re.sub(r"[^\d]", "", price_whole.get_text(strip=True))
            frac  = re.sub(r"[^\d]", "", price_frac.get_text(strip=True)) if price_frac else "00"
            return float(f"{whole}.{frac or '00'}")
        except Exception:
            pass

    return None


def _find_title(item) -> str | None:
    """
    Extrai o título do card da Amazon.
    O h2 no HTML atual não tem filho <a> — o texto está direto no h2 ou em span filho.
    O link <a> está como irmão ou em outro nível do DOM.
    """
    # Tentativa 1: span com data-cy (mais semântico)
    recipe = item.select_one("[data-cy='title-recipe'] span")
    if recipe:
        return recipe.get_text(strip=True)

    # Tentativa 2: qualquer span dentro do h2
    h2 = item.find("h2")
    if h2:
        span = h2.find("span")
        if span:
            return span.get_text(strip=True)
        # Se não há span, usa o texto direto do h2
        texto = h2.get_text(strip=True)
        if texto:
            return texto

    # Tentativa 3: atributo aria-label do link principal
    link = item.select_one("a.a-link-normal[href*='/dp/']")
    if link and link.get("aria-label"):
        return link.get("aria-label")

    return None


def _find_link(item) -> str | None:
    """
    Encontra o link do produto.
    Na Amazon BR o <a> com href para /dp/ ou /gp/ é o link do produto.
    """
    # Link por padrão de URL de produto (/dp/ ou /gp/product/)
    for a in item.select("a.a-link-normal"):
        href = a.get("href", "")
        if "/dp/" in href or "/gp/product/" in href:
            if not href.startswith("http"):
                href = "https://www.amazon.com.br" + href
            return href

    # Fallback: qualquer link dentro do h2
    h2 = item.find("h2")
    if h2:
        a = h2.find("a")
        if a:
            href = a.get("href", "")
            if not href.startswith("http"):
                href = "https://www.amazon.com.br" + href
            return href

    return None


def search_amazon(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos na Amazon BR pela página de resultados.
    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    url = f"https://www.amazon.com.br/s?k={query.replace(' ', '+')}"
    results = []

    try:
        headers = random.choice(HEADERS_POOL)
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup  = BeautifulSoup(response.text, "lxml")
        items = soup.select("div[data-component-type='s-search-result']")

        for item in items[:max_results]:
            try:
                title    = _find_title(item)
                href     = _find_link(item)
                image_el = item.select_one("img.s-image")

                if not title or not href:
                    continue

                price = _parse_amazon_price(item)

                # Rating: "4,5 de 5 estrelas"
                rating = None
                rating_el = item.select_one("span.a-icon-alt")
                if rating_el:
                    try:
                        rating = float(
                            rating_el.get_text(strip=True).split(" ")[0].replace(",", ".")
                        )
                    except Exception:
                        pass

                # Contagem de reviews
                reviews = None
                reviews_el = item.select_one("span.a-size-base.s-underline-text")
                if reviews_el:
                    try:
                        reviews = int(re.sub(r"[^\d]", "", reviews_el.get_text(strip=True)))
                    except Exception:
                        pass

                results.append({
                    "store":        "amazon",
                    "title":        title,
                    "product_url":  href,
                    "price":        price,
                    "currency":     "BRL",
                    "image_url":    image_el.get("src") if image_el else None,
                    "rating":       rating,
                    "review_count": reviews,
                })
            except Exception:
                continue

    except Exception:
        logger.exception("amazon_search | erro ao buscar | query='%s'", query)

    logger.info("amazon_search | %d resultados | query='%s'", len(results), query)
    return results
