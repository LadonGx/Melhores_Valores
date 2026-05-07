# Mercado Livre Adapter
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


def _parse_price_from_soup(soup) -> float | None:
    """
    Extrai o preço de uma página de produto do Mercado Livre.
    Usa estratégias da mais confiável para a mais específica, sem fallbacks genéricos
    que possam capturar preços errados (parcelas, comparativos, etc).
    """
    # Estratégia 1: meta tag itemprop="price" — padrão schema.org, mais confiável
    meta = soup.find("meta", {"itemprop": "price"})
    if meta and meta.get("content"):
        try:
            val = float(str(meta["content"]).replace(",", "."))
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    # Estratégia 2: seletor específico do bloco de preço principal da página de produto
    # .ui-pdp-price__second-line contém o preço de compra, não parcelas ou comparativos
    main_price_block = soup.select_one(".ui-pdp-price__second-line")
    if main_price_block:
        # Tenta o aria-label primeiro (ex: "30 reais")
        amount_el = main_price_block.select_one("span.andes-money-amount[aria-label]")
        if amount_el:
            try:
                label = amount_el.get("aria-label", "")
                nums = re.findall(r"\d+", label)
                if len(nums) >= 2:
                    return float(f"{nums[0]}.{nums[1].zfill(2)}")
                elif len(nums) == 1:
                    return float(nums[0])
            except (ValueError, TypeError):
                pass

        # Tenta fração + centavos dentro do bloco correto
        fraction_el = main_price_block.select_one(".andes-money-amount__fraction")
        if fraction_el:
            try:
                whole = re.sub(r"[^\d]", "", fraction_el.get_text(strip=True))
                cents_el = main_price_block.select_one(".andes-money-amount__cents")
                cents = re.sub(r"[^\d]", "", cents_el.get_text(strip=True)) if cents_el else "00"
                val = float(f"{whole}.{cents or '00'}")
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass

    # Estratégia 3: container principal alternativo (páginas catalog /p/)
    price_container = soup.select_one(".ui-pdp-price__main-container")
    if price_container:
        amount_el = price_container.select_one("span.andes-money-amount[aria-label]")
        if amount_el:
            try:
                label = amount_el.get("aria-label", "")
                nums = re.findall(r"\d+", label)
                if len(nums) >= 2:
                    return float(f"{nums[0]}.{nums[1].zfill(2)}")
                elif len(nums) == 1:
                    return float(nums[0])
            except (ValueError, TypeError):
                pass

    # Não encontrado — retorna None para sinalizar falha ao orquestrador
    return None


def extract_from_html(html: str) -> dict | None:
    """
    Extrai preço e metadados do HTML bruto de uma página de produto do Mercado Livre.
    """
    soup = BeautifulSoup(html, "lxml")

    # Guardrail: detectar redirecionamento para página de login ou bloqueio
    page_title = soup.title.get_text(strip=True) if soup.title else ""
    if any(kw in page_title.lower() for kw in ("acesse sua conta", "faça seu login", "acesso negado", "bloqueado")):
        print("[mercadolivre adapter] Bloqueio/login detectado.")
        return None

    try:
        # Título — seletor específico de página de produto ML
        title_el = soup.select_one(".ui-pdp-title") or soup.select_one("h1.ui-pdp-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else None

        price = _parse_price_from_soup(soup)
        if price is None:
            print("[mercadolivre adapter] Preço não encontrado com seletores específicos.")
            return None

        # Imagem principal
        img_el = soup.select_one(".ui-pdp-gallery__figure__image") or soup.select_one("figure.ui-pdp-gallery__figure img")
        image_url = img_el.get("src") or img_el.get("data-zoom") if img_el else None

        return {
            "title": title,
            "price": price,
            "currency": "BRL",
            "image_url": image_url,
        }
    except Exception as e:
        print(f"[mercadolivre adapter] Erro ao extrair: {e}")
        return None
