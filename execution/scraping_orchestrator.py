from execution.scrapers.base_scraper import fetch_html_simple
from execution.scrapers.playwright_scraper import fetch_html_playwright
from execution.firecrawl_api import scrape_product_data
from execution.store_detection import detect_store_from_url as detect_store
from execution.adapters import amazon, mercadolivre, aliexpress

ADAPTERS = {
    "amazon": amazon.extract_from_html,
    "mercadolivre": mercadolivre.extract_from_html,
    "aliexpress": aliexpress.extract_from_html,
}

# Lojas que renderizam preços via JavaScript e precisam pular o Nível 1
JS_REQUIRED_STORES = {"mercadolivre", "aliexpress"}

def scrape_product(url: str, store: str = None) -> dict | None:
    """
    Orquestra o scraping em cascata:
      Nível 1 → httpx simples    (grátis, ~1s)
      Nível 2 → Playwright       (grátis, ~5-8s)
      Nível 3 → Firecrawl API    (pago, último recurso)
    """
    if not store:
        store = detect_store(url)
    adapter = ADAPTERS.get(store)

    if not adapter:
        print(f"[orchestrator] Loja não suportada: {store}")
        return None

    # --- Nível 1: httpx simples ---
    if store not in JS_REQUIRED_STORES:
        print(f"[orchestrator] Tentativa 1: httpx simples para {store}")
        html = fetch_html_simple(url)
        if html:
            result = adapter(html)
            if result and result.get("price") is not None:
                print(f"[orchestrator] ✅ Sucesso no nível 1 (httpx)")
                return result

    # --- Nível 2: Playwright ---
    print(f"[orchestrator] Tentativa 2: Playwright para {store}")
    html = fetch_html_playwright(url)
    if html:
        result = adapter(html)
        if result and result.get("price") is not None:
            print(f"[orchestrator] ✅ Sucesso no nível 2 (Playwright)")
            return result

    # --- Nível 3: Firecrawl (último recurso) ---
    print(f"[orchestrator] ⚠️ Tentativa 3: Firecrawl (consumindo crédito) para {store}")
    return scrape_product_data(url)
