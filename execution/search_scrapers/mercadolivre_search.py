import httpx
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


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
    Busca produtos no Mercado Livre BR pela página de listagem.
    Retorna lista normalizada de dicts prontos para salvar via db_client.
    """
    url = f"https://lista.mercadolivre.com.br/{query.replace(' ', '-')}"
    results = []

    try:
        with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        soup  = BeautifulSoup(response.text, "lxml")
        items = soup.select("li.ui-search-layout__item")

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

    except Exception as e:
        print(f"[mercadolivre_search] Erro: {e}")

    print(f"[mercadolivre_search] {len(results)} resultados para '{query}'")
    return results
