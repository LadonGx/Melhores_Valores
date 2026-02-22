import os

import requests
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1/scrape")


def scrape_product_data(url: str):
    """
    Realiza a chamada para a API do Firecrawl para extrair dados brutos da URL.
    Retorna o JSON bruto da extração.
    """
    if not FIRECRAWL_API_KEY:
        return {}

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"url": url, "formats": ["markdown", "html"]}

    try:
        response = requests.post(
            FIRECRAWL_BASE_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {}
