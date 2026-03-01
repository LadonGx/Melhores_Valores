import httpx
from bs4 import BeautifulSoup
import random

HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    },
]

def fetch_html_simple(url: str) -> str | None:
    """
    Nível 1 da cascata: requisição HTTP simples com headers rotacionados.
    Ideal para páginas que não dependem de JavaScript para renderizar o preço.
    """
    headers = random.choice(HEADERS_POOL)
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        print(f"[base_scraper] Falhou para {url}: {e}")
        return None
