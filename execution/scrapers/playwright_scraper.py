from playwright.sync_api import sync_playwright

def fetch_html_playwright(url: str, wait_ms: int = 3000) -> str | None:
    """
    Nível 2 da cascata: renderização completa com Playwright.
    Usa domcontentloaded (mais rápido e confiável que networkidle) e aguarda
    um tempo fixo para execução de JS assíncrono após o carregamento inicial.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="pt-BR",
                # Bloquear recursos desnecessários para acelerar carregamento
                java_script_enabled=True,
            )
            # Bloquear fontes, imagens e analytics para acelerar carregamento
            def block_unnecessary(route):
                if route.request.resource_type in ("image", "font", "media"):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", block_unnecessary)
            page = context.new_page()
            # domcontentloaded: aguarda só o HTML/CSS, sem esperar requests assíncronos infinitos
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Aguarda JS renderizar o preço no DOM
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"[playwright_scraper] Falhou para {url}: {e}")
        return None
