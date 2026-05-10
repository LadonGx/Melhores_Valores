import os

import httpx
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1/scrape")


def scrape_product_data(url: str):
    if not FIRECRAWL_API_KEY:
        return {}

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
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

    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(FIRECRAWL_BASE_URL, json=payload, headers=headers)
            response.raise_for_status()

        res_json = response.json()
        extracted = res_json.get("data", {}).get("extract", {})
        return {"data": {"metadata": extracted}}
    except httpx.HTTPError as e:
        print(f"Erro no Firecrawl: {e}")
        return {}
