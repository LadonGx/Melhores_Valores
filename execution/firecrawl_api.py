import logging
import os

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

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
                    "available": {
                        "type": "boolean",
                        "description": (
                            "Whether the product is currently in stock and available for "
                            "purchase. False if the page shows any out-of-stock/"
                            "unavailable/sold-out message."
                        ),
                    },
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
        logger.error("Firecrawl | erro HTTP | url=%s | error=%s", url, e)
        return {}
