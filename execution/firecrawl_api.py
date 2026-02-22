import os
import requests
from dotenv import load_dotenv

load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

def scrape_product_data(url: str):
    """
    Realiza a chamada para a API do Firecrawl para extrair dados brutos da URL.
    Retorna o JSON bruto da extração.
    """
    # TODO: Implementar request autenticado ao Firecrawl
    return {}
