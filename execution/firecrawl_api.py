import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1/scrape")


def _post_firecrawl(payload: dict[str, Any]) -> dict[str, Any]:
    if not FIRECRAWL_API_KEY:
        return {}

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            FIRECRAWL_BASE_URL,
            json=payload,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"Erro no Firecrawl: {exc}")
        return {}


def scrape_product_data(url: str):
    """Realiza a chamada para a API do Firecrawl para extrair dados brutos da URL."""
    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "price": {"type": "number"},
                },
                "required": ["title", "price"],
            }
        },
    }

    res_json = _post_firecrawl(payload)
    extracted = res_json.get("data", {}).get("extract", {})

    return {"data": {"metadata": extracted}}


def scrape_search_results(url: str, limit: int = 10) -> list[dict[str, Any]]:
    """Extrai itens de listagem (nome, preço e URL) de uma página de busca."""
    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {
            "schema": {
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                                "price": {"type": "number"},
                                "imageUrl": {"type": "string"},
                            },
                            "required": ["name", "url"],
                        },
                    }
                },
                "required": ["products"],
            }
        },
    }

    response_json = _post_firecrawl(payload)
    extracted = response_json.get("data", {}).get("extract", {})
    products = extracted.get("products", []) if isinstance(extracted, dict) else []

    if not isinstance(products, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for item in products:
        if not isinstance(item, dict):
            continue

        product_url = item.get("url")
        product_name = item.get("name")
        if not isinstance(product_url, str) or not product_url.strip():
            continue
        if not isinstance(product_name, str) or not product_name.strip():
            continue

        price = item.get("price")
        image_url = item.get("imageUrl")

        cleaned.append(
            {
                "name": product_name.strip(),
                "url": product_url.strip(),
                "price": float(price) if isinstance(price, (int, float)) else None,
                "image_url": image_url.strip() if isinstance(image_url, str) else None,
            }
        )

        if len(cleaned) >= limit:
            break

    return cleaned
