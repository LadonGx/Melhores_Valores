import logging

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Script executado antes de qualquer JS da página para ocultar sinais de automação
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US'] });
window.chrome = { runtime: {} };
"""


def fetch_html_playwright(
    url: str,
    wait_ms: int = 3000,
    wait_for_selectors: tuple[str, ...] | None = None,
    warmup_url: str | None = None,
) -> str | None:
    """
    Nível 2 da cascata: renderização completa com Playwright.
    Usa domcontentloaded (mais rápido e confiável que networkidle) e aguarda
    um tempo fixo para execução de JS assíncrono após o carregamento inicial.

    Inclui evasão básica de anti-bot: remove navigator.webdriver e outros
    sinais de automação que sites como Magalu e Mercado Livre detectam.

    Args:
        wait_for_selectors: seletores a aguardar após o load (substitui os
            seletores padrão de página de produto — útil para páginas de
            listagem/busca, que nunca têm esses seletores).
        warmup_url: se informado, é visitada antes de `url` no mesmo contexto/
            sessão, para estabelecer cookies como uma navegação orgânica faria.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="pt-BR",
                java_script_enabled=True,
                viewport={"width": 1280, "height": 800},
            )
            # Injeta o script de evasão antes de qualquer JS da página
            context.add_init_script(_STEALTH_JS)

            # Bloquear fontes, imagens e media para acelerar carregamento
            def block_unnecessary(route):
                if route.request.resource_type in ("image", "font", "media"):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", block_unnecessary)
            page = context.new_page()
            if warmup_url:
                # Visita a home primeiro para estabelecer cookies/sessão antes do
                # request "suspeito" ir direto para a página alvo (reduz a chance
                # de acionar muralhas anti-bot em páginas de listagem/busca).
                try:
                    page.goto(warmup_url, timeout=15000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
            # domcontentloaded: aguarda só o HTML/CSS, sem esperar requests assíncronos infinitos
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Aguarda JS renderizar o conteúdo no DOM (baseline)
            page.wait_for_timeout(wait_ms)
            # Garante que qualquer redirect JS já finalizou antes de extrair HTML
            try:
                page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            # Aguarda um elemento de preço aparecer no DOM (útil para páginas de catálogo
            # com preço renderizado por componentes assíncronos como ML /p/ e /up/).
            # Se não aparecer em 5s, extrai o que já estiver disponível.
            _PRICE_SELECTORS = (
                "meta[itemprop='price']",
                "span.priceToPay",
                "span.a-offscreen",
                ".ui-pdp-price__second-line",
                "[class*='currentPriceText']",
            )
            for sel in (wait_for_selectors or _PRICE_SELECTORS):
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    break
                except Exception:
                    continue
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.warning("playwright_scraper | falhou | url=%s | error=%s", url, e)
        return None
