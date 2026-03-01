# Amazon Adapter

from bs4 import BeautifulSoup

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


def extract_from_html(html: str) -> dict | None:
    """
    Extrai preço e metadados do HTML bruto de uma página de produto da Amazon.
    Retorna None se os seletores não encontrarem os dados esperados.
    """
    soup = BeautifulSoup(html, "lxml")

    try:
        price_whole = soup.select_one("span.a-price-whole")
        price_fraction = soup.select_one("span.a-price-fraction")

        if not price_whole:
            return None

        price_str = price_whole.get_text(strip=True).replace(".", "").replace(",", "")
        fraction_str = price_fraction.get_text(strip=True) if price_fraction else "00"
        price = float(f"{price_str}.{fraction_str}")

        title = soup.select_one("#productTitle")
        title_text = title.get_text(strip=True) if title else "Produto Amazon"

        image = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
        image_url = image.get("src") or image.get("data-src") if image else None

        return {
            "title": title_text,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
        }
    except Exception as e:
        print(f"[amazon adapter] Erro ao extrair: {e}")
        return None
