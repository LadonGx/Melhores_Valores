# AliExpress Adapter

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
    Extrai preço e metadados do HTML bruto de uma página de produto do AliExpress.
    """
    soup = BeautifulSoup(html, "lxml")
    try:
        title_elem = soup.select_one("h1[data-pl='product-title']")
        title = title_elem.get_text(strip=True) if title_elem else "Produto AliExpress"
        
        price_elem = (
            soup.select_one("[class*='currentPriceText']")
            or soup.select_one("[class*='product-price-value']")
        )
        if not price_elem:
            return None

        price_str = price_elem.get_text(strip=True).replace("R$", "").replace(".", "").replace(",", ".").strip()
        price = float(price_str)

        img_elem = soup.select_one("[class*='magnifier--image']") or soup.select_one(".magnifier-image")
        image_url = img_elem.get("src") if img_elem else None
        
        return {
            "name": title,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
        }
    except Exception as e:
        print(f"[aliexpress adapter] Erro ao extrair: {e}")
        return None
