# Amazon Adapter
import re
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


def _parse_price_text(text: str) -> float | None:
    """Converte 'R$ 30,00' ou '30,00' para float 30.0."""
    try:
        cleaned = re.sub(r"[R$\s\xa0]", "", text)
        cleaned = cleaned.replace(".", "").replace(",", ".")
        val = float(cleaned)
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def _extract_price_from_soup(soup) -> float | None:
    """
    Extrai o preço ATUAL (não o preço original riscado) de uma página de produto Amazon.

    A Amazon usa `span.a-price.a-text-strike` para o preço original riscado e
    `span.a-price` sem essa classe para o preço atual.
    A forma mais confiável é ler `span.a-offscreen` dentro de um `span.a-price`
    que NÃO tenha a classe `a-text-strike`.
    """
    # Estratégia 1: encontrar todos os span.a-price e pegar o primeiro que NÃO é tachado
    for price_span in soup.select("span.a-price"):
        if "a-text-strike" in price_span.get("class", []):
            continue  # pula o preço riscado (preço original "de")
        offscreen = price_span.select_one("span.a-offscreen")
        if offscreen:
            val = _parse_price_text(offscreen.get_text(strip=True))
            if val:
                return val

    # Estratégia 2: bloco de preço principal de produto (#corePrice_feature_div)
    core_price = soup.select_one("#corePrice_feature_div")
    if core_price:
        offscreen = core_price.select_one("span.a-offscreen")
        if offscreen:
            val = _parse_price_text(offscreen.get_text(strip=True))
            if val:
                return val

    # Estratégia 3: bloco "nosso preço" (layout mais antigo)
    for price_id in ("#priceblock_ourprice", "#priceblock_dealprice", "#price_inside_buybox"):
        el = soup.select_one(price_id)
        if el:
            val = _parse_price_text(el.get_text(strip=True))
            if val:
                return val

    # Estratégia 4: seletores clássicos separados (whole + fraction), evitando tachados
    price_whole = soup.select_one("span.a-price:not(.a-text-strike) span.a-price-whole")
    if price_whole:
        try:
            whole = re.sub(r"[^\d]", "", price_whole.get_text(strip=True))
            fraction_el = soup.select_one("span.a-price:not(.a-text-strike) span.a-price-fraction")
            frac = re.sub(r"[^\d]", "", fraction_el.get_text(strip=True)) if fraction_el else "00"
            val = float(f"{whole}.{frac or '00'}")
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    return None


def extract_from_html(html: str) -> dict | None:
    """
    Extrai preço e metadados do HTML bruto de uma página de produto da Amazon.
    Retorna None se os seletores não encontrarem os dados esperados.
    """
    soup = BeautifulSoup(html, "lxml")

    try:
        price = _extract_price_from_soup(soup)
        if price is None:
            print("[amazon adapter] Preço não encontrado.")
            return None

        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else None

        image_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
        image_url = (image_el.get("src") or image_el.get("data-src")) if image_el else None

        return {
            "title": title,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
        }
    except Exception as e:
        print(f"[amazon adapter] Erro ao extrair: {e}")
        return None
