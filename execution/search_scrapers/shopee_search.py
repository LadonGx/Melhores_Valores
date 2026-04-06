"""
Busca de produtos em lojas adicionais (Magazine Luiza substituindo Shopee).

Contexto: A Shopee é uma SPA React pura sem SSR e sua API interna requer
sessão autenticada (403). Em vez de tentar scraping impossível, usamos o
Magazine Luiza como terceira loja. O Magalu renderiza os dados em um bloco
script JSON estruturado (__NEXT_DATA__).
"""
import httpx
from bs4 import BeautifulSoup
import json
import warnings

# Opressão de warning de certificado que pode acontecer em ALGUNS ambientes docker
warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def search_shopee(query: str, max_results: int = 10) -> list[dict]:
    """
    Busca produtos no Magazine Luiza (substituto da Shopee).
    Extrai os dados do bloco JSON embutido (__NEXT_DATA__).

    Retorna lista normalizada de dicts prontos para salvar via db_client.
    O campo 'store' é definido como 'magalu' para refletir a fonte real.
    """
    results = []

    try:
        url = f"https://www.magazineluiza.com.br/busca/{query.replace(' ', '%20')}/"

        with httpx.Client(
            timeout=20,
            headers=HEADERS,
            follow_redirects=True,
            verify=False,   # Previne problemas com certificados em ALGUNS dockers
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        next_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        
        if not next_tag or not next_tag.string:
            print("[magalu_search] Não foi possível encontrar o __NEXT_DATA__")
            return results

        data = json.loads(next_tag.string)
        
        # Acesso seguro à estrutura de produtos
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        data_props = page_props.get("data", {})
        search_props = data_props.get("search", {})
        products = search_props.get("products", [])

        for prod in products[:max_results]:
            try:
                title = prod.get("title")
                path = prod.get("path", "")
                
                if not title or not path:
                    continue
                    
                href = f"https://www.magazineluiza.com.br{path}"

                # Imagens no formato de template {w}x{h}
                img_src = prod.get("image")
                if img_src:
                    img_src = img_src.replace("{w}", "300").replace("{h}", "300")

                # Preço
                price_info = prod.get("price", {})
                price_str = price_info.get("bestPrice") or price_info.get("price")
                price = float(price_str) if price_str else None

                # Avaliações
                rating_info = prod.get("rating", {})
                rating = rating_info.get("score")
                rating = float(rating) if rating else None
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

    except Exception as e:
        print(f"[magalu_search] Erro: {e}")

    print(f"[magalu_search] {len(results)} resultados para '{query}'")
    return results
