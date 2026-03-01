# Mercado Livre Adapter

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
    Extrai preço e metadados do HTML bruto de uma página de produto do Mercado Livre.
    Usa múltiplas estratégias para ser resiliente a mudanças de layout.
    """
    soup = BeautifulSoup(html, "lxml")

    # Guardrail: detectar redirecionamento para página de login
    page_title = soup.title.get_text(strip=True) if soup.title else ""
    if "acesse sua conta" in page_title.lower() or "faça seu login" in page_title.lower():
        print("[mercadolivre adapter] Página de login detectada — bloqueio anti-bot.")
        return None

    try:
        # Título
        title_elem = soup.select_one(".ui-pdp-title") or soup.select_one("h1")
        title = title_elem.get_text(strip=True) if title_elem else "Produto Mercado Livre"

        # Estratégia 1: meta tag com itemprop="price" — mais confiável
        meta_price = soup.find("meta", {"itemprop": "price"})
        if meta_price and meta_price.get("content"):
            price = float(meta_price["content"])
        else:
            # Estratégia 2: seletores CSS de fração + centavos
            price_fraction = soup.select_one(".ui-pdp-price__second-line .andes-money-amount__fraction")
            if not price_fraction:
                # Último recurso: qualquer fração de preço visível
                price_fraction = soup.select_one(".andes-money-amount__fraction")
            if not price_fraction:
                return None

            price_str = price_fraction.get_text(strip=True).replace(".", "")
            cents_elem = soup.select_one(".ui-pdp-price__second-line .andes-money-amount__cents")
            cents_str = cents_elem.get_text(strip=True) if cents_elem else "00"
            price = float(f"{price_str}.{cents_str}")

        # Imagem
        img_elem = soup.select_one(".ui-pdp-gallery__figure__image")
        image_url = img_elem.get("src") if img_elem else None

        return {
            "title": title,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
        }
    except Exception as e:
        print(f"[mercadolivre adapter] Erro ao extrair: {e}")
        return None
