"""
Busca de produtos no Magazine Luiza.

Contexto: A Shopee é uma SPA React pura sem SSR e sua API interna requer
sessão autenticada (403). Em vez de tentar scraping impossível, usamos o
Magazine Luiza como terceira loja.

O Magalu bloqueia requisições httpx com 403. Usamos Playwright (renderização
completa com Chromium) para contornar o bloqueio e então extraímos os dados
do bloco script JSON (__NEXT_DATA__) presente no HTML renderizado.
"""
import json
import re

from bs4 import BeautifulSoup

from execution.scrapers.playwright_scraper import fetch_html_playwright


def search_shopee(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos no Magazine Luiza (substituto da Shopee).

    Usa Playwright para contornar o bloqueio anti-bot (403 com httpx).
    Extrai os dados do bloco JSON __NEXT_DATA__ no HTML renderizado.

    Retorna lista normalizada de dicts prontos para salvar via db_client.
    O campo 'store' é definido como 'magalu' para refletir a fonte real.
    """
    results = []

    # Codifica a query preservando espaços como %20 (formato esperado pelo Magalu)
    encoded = query.replace(" ", "%20")
    url = f"https://www.magazineluiza.com.br/busca/{encoded}/"

    html = fetch_html_playwright(url, wait_ms=3000)
    if not html:
        print(f"[magalu_search] Playwright não retornou HTML para '{query}'")
        return results

    soup = BeautifulSoup(html, "lxml")

    # Estratégia 1: extrair do __NEXT_DATA__ JSON (mais completo)
    next_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if next_tag and next_tag.string:
        try:
            data = json.loads(next_tag.string)

            props       = data.get("props", {})
            page_props  = props.get("pageProps", {})
            data_props  = page_props.get("data", {})
            search_data = data_props.get("search", {})
            products    = search_data.get("products", [])

            for prod in products[:max_results]:
                try:
                    title = prod.get("title")
                    path  = prod.get("path", "")

                    if not title or not path:
                        continue

                    href = f"https://www.magazineluiza.com.br{path}"

                    # Imagens no formato de template {w}x{h}
                    img_src = prod.get("image")
                    if img_src:
                        img_src = img_src.replace("{w}", "300").replace("{h}", "300")

                    # Preço
                    price_info = prod.get("price", {})
                    price_str  = price_info.get("bestPrice") or price_info.get("price")
                    price      = float(price_str) if price_str else None

                    # Avaliações
                    rating_info = prod.get("rating", {})
                    rating  = rating_info.get("score")
                    rating  = float(rating) if rating else None
                    reviews = rating_info.get("count")
                    reviews = int(reviews) if reviews else None

                    results.append({
                        "store":        "magalu",
                        "title":        title,
                        "product_url":  href,
                        "price":        price,
                        "currency":     "BRL",
                        "image_url":    img_src,
                        "rating":       rating,
                        "review_count": reviews,
                    })
                except Exception:
                    continue

            if results:
                print(f"[magalu_search] {len(results)} resultados via __NEXT_DATA__ para '{query}'")
                return results

        except Exception as e:
            print(f"[magalu_search] Falha ao parsear __NEXT_DATA__: {e}")

    # Estratégia 2: CSS selectors no HTML renderizado
    cards = soup.select("[data-testid='product-card']")
    if not cards:
        # Tenta seletores alternativos conhecidos do Magalu
        cards = soup.select("li[class*='productCard']") or soup.select("a[class*='ProductCard']")

    for card in cards[:max_results]:
        try:
            title_el = card.select_one("h2") or card.select_one("[class*='title']")
            link_el  = card if card.name == "a" else card.select_one("a[href]")
            price_el = card.select_one("[class*='price']") or card.select_one("[data-testid*='price']")

            title = title_el.get_text(strip=True) if title_el else None
            href  = link_el.get("href", "") if link_el else None
            if not title or not href:
                continue

            if not href.startswith("http"):
                href = f"https://www.magazineluiza.com.br{href}"

            price = None
            if price_el:
                try:
                    raw = re.sub(r"[^\d,]", "", price_el.get_text(strip=True))
                    price = float(raw.replace(",", ".")) if raw else None
                except Exception:
                    pass

            results.append({
                "store":        "magalu",
                "title":        title,
                "product_url":  href,
                "price":        price,
                "currency":     "BRL",
                "image_url":    None,
                "rating":       None,
                "review_count": None,
            })
        except Exception:
            continue

    print(f"[magalu_search] {len(results)} resultados via CSS para '{query}'")
    return results
