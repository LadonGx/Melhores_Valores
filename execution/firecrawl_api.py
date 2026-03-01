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
    payload = {
        "url": url, 
        "formats": ["extract"],
        "extract": {
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "price": {"type": "number"}
                },
                "required": ["title", "price"]
            }
        }
    }

    try:
        response = requests.post(
            FIRECRAWL_BASE_URL,
            json=payload,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        
        # Firecrawl returns data in response.json()["data"]["extract"]
        res_json = response.json()
        extracted = res_json.get("data", {}).get("extract", {})
        
        # Mapeia o resultado para o formato que os adaptadores já esperam
        return {
            "data": {
                "metadata": extracted
            }
        }
    except requests.RequestException as e:
        print(f"Erro no Firecrawl: {e}")
        return {}
