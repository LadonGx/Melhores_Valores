"""
Unit tests for the two fetch strategies used by the scraping cascade.

Contract under test: `fetch_html_simple` and `fetch_html_playwright` must
NEVER raise — any network/browser failure is caught internally and turned
into a `None` return, so `scraping_orchestrator.py` can escalate to the next
level of the cascade. All network/browser calls are mocked; no test touches
the real internet.
"""

from unittest.mock import patch, MagicMock

import pytest

from execution.scrapers import playwright_scraper
from execution.scrapers.base_scraper import fetch_html_simple
from execution.scrapers.playwright_scraper import fetch_html_playwright


# ─── fetch_html_simple (httpx) ─────────────────────────────────────────────

class TestFetchHtmlSimple:
    def test_success_returns_response_text(self):
        mock_response = MagicMock()
        mock_response.text = "<html>ok</html>"
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        with patch("execution.scrapers.base_scraper.httpx.Client", return_value=mock_client):
            result = fetch_html_simple("https://www.amazon.com.br/dp/test")

        assert result == "<html>ok</html>"

    def test_http_error_status_returns_none(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        with patch("execution.scrapers.base_scraper.httpx.Client", return_value=mock_client):
            result = fetch_html_simple("https://www.amazon.com.br/dp/test")

        assert result is None

    def test_network_error_returns_none(self):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection refused")

        with patch("execution.scrapers.base_scraper.httpx.Client", return_value=mock_client):
            result = fetch_html_simple("https://www.amazon.com.br/dp/test")

        assert result is None


# ─── fetch_html_playwright ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_browser_choice():
    """A escolha do navegador é guardada no módulo; cada teste começa do zero."""
    playwright_scraper._reset_browser_choice()
    yield
    playwright_scraper._reset_browser_choice()


def _mock_playwright_chain(html: str | None = None, goto_side_effect=None):
    """Builds a MagicMock chain matching:
    sync_playwright() -> chromium.launch() -> new_context() -> new_page()
    """
    mock_page = MagicMock()
    mock_page.content.return_value = html
    # Selector wait always "fails" (element never appears) — the function
    # treats this as non-fatal and falls through to page.content().
    mock_page.wait_for_selector.side_effect = Exception("selector not found")
    mock_page.wait_for_load_state.side_effect = Exception("timeout")
    if goto_side_effect is not None:
        mock_page.goto.side_effect = goto_side_effect

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser

    mock_p = MagicMock()
    mock_p.chromium = mock_chromium

    mock_sync_playwright_cm = MagicMock()
    mock_sync_playwright_cm.__enter__.return_value = mock_p

    return mock_sync_playwright_cm


class TestFetchHtmlPlaywright:
    def test_success_returns_page_content(self):
        chain = _mock_playwright_chain(html="<html>rendered</html>")

        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            result = fetch_html_playwright("https://lista.mercadolivre.com.br/notebook")

        assert result == "<html>rendered</html>"

    def test_navigation_failure_returns_none(self):
        chain = _mock_playwright_chain(goto_side_effect=Exception("Timeout 30000ms exceeded"))

        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            result = fetch_html_playwright("https://lista.mercadolivre.com.br/notebook")

        assert result is None

    def test_browser_launch_failure_returns_none(self):
        with patch("execution.scrapers.playwright_scraper.sync_playwright") as mock_sync_playwright:
            mock_sync_playwright.side_effect = Exception("Executable doesn't exist")
            result = fetch_html_playwright("https://lista.mercadolivre.com.br/notebook")

        assert result is None

    def test_wait_for_selectors_overrides_default_product_selectors(self):
        """Listing/search pages need their own selectors (li.ui-search-layout__item, etc.),
        never the hardcoded product-page selectors — otherwise every search wastes ~25s
        waiting for selectors that can never appear on a listing page."""
        chain = _mock_playwright_chain(html="<html>rendered</html>")
        mock_page = chain.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value

        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            fetch_html_playwright(
                "https://lista.mercadolivre.com.br/notebook",
                wait_for_selectors=("li.ui-search-layout__item", "span.andes-money-amount"),
            )

        waited_selectors = [call.args[0] for call in mock_page.wait_for_selector.call_args_list]
        assert waited_selectors == ["li.ui-search-layout__item", "span.andes-money-amount"]

    def test_warmup_url_is_visited_before_target_url(self):
        """warmup_url should be navigated first (to establish cookies/session) before
        the real target URL — used to reduce anti-bot false positives on listing pages."""
        chain = _mock_playwright_chain(html="<html>rendered</html>")
        mock_page = chain.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value

        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            fetch_html_playwright(
                "https://lista.mercadolivre.com.br/notebook",
                warmup_url="https://www.mercadolivre.com.br/",
            )

        goto_urls = [call.args[0] for call in mock_page.goto.call_args_list]
        assert goto_urls == [
            "https://www.mercadolivre.com.br/",
            "https://lista.mercadolivre.com.br/notebook",
        ]

    def test_no_warmup_url_navigates_only_to_target(self):
        chain = _mock_playwright_chain(html="<html>rendered</html>")
        mock_page = chain.__enter__.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value

        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            fetch_html_playwright("https://lista.mercadolivre.com.br/notebook")

        goto_urls = [call.args[0] for call in mock_page.goto.call_args_list]
        assert goto_urls == ["https://lista.mercadolivre.com.br/notebook"]


# ─── Escolha do navegador (Edge → Chrome → Chromium do Playwright) ─────────

def _chain_with_launch(launch_side_effect):
    """Cadeia do Playwright em que chromium.launch(**kwargs) segue `launch_side_effect`."""
    chain = _mock_playwright_chain(html="<html>ok</html>")
    chromium = chain.__enter__.return_value.chromium
    browser = chromium.launch.return_value
    chromium.launch.side_effect = lambda **kw: launch_side_effect(kw, browser)
    return chain, chromium


def _available(*channels):
    """launch() funciona só para os canais listados (None = Chromium do Playwright)."""
    def side_effect(kwargs, browser):
        channel = kwargs.get("channel")
        if channel in channels:
            return browser
        raise Exception(f"Chromium distribution '{channel}' is not found\nmais detalhes")
    return side_effect


def _channels_tried(chromium):
    return [c.kwargs.get("channel") for c in chromium.launch.call_args_list]


class TestBrowserSelection:
    def test_prefers_edge_and_remembers_it(self):
        chain, chromium = _chain_with_launch(_available("msedge", "chrome", None))
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            assert fetch_html_playwright("https://a") == "<html>ok</html>"
            assert fetch_html_playwright("https://b") == "<html>ok</html>"

        assert _channels_tried(chromium) == ["msedge", "msedge"]
        assert playwright_scraper.browser_in_use() == "Microsoft Edge"

    def test_launch_keeps_headless_and_anti_automation_args(self):
        chain, chromium = _chain_with_launch(_available("msedge"))
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            fetch_html_playwright("https://a")

        kwargs = chromium.launch.call_args.kwargs
        assert kwargs["headless"] is True
        assert "--disable-blink-features=AutomationControlled" in kwargs["args"]

    def test_falls_back_to_chrome_without_edge(self):
        chain, chromium = _chain_with_launch(_available("chrome", None))
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            assert fetch_html_playwright("https://a") == "<html>ok</html>"
            fetch_html_playwright("https://b")

        assert _channels_tried(chromium) == ["msedge", "chrome", "chrome"]
        assert playwright_scraper.browser_in_use() == "Google Chrome"

    def test_falls_back_to_playwright_chromium_without_channel(self):
        chain, chromium = _chain_with_launch(_available(None))
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            assert fetch_html_playwright("https://a") == "<html>ok</html>"

        assert _channels_tried(chromium) == ["msedge", "chrome", None]
        assert "channel" not in chromium.launch.call_args.kwargs

    def test_no_browser_returns_none_and_stops_trying(self, caplog):
        chain, chromium = _chain_with_launch(_available())
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            assert fetch_html_playwright("https://a") is None
            assert fetch_html_playwright("https://b") is None

        assert _channels_tried(chromium) == ["msedge", "chrome", None]  # só na 1ª chamada
        assert playwright_scraper.browser_in_use() is None
        assert "nenhum navegador disponível" in caplog.text

    def test_detection_is_retried_after_cooldown(self):
        """Falha passageira (ex: Edge atualizando) não desliga o nível 2 até reiniciar o app."""
        state = {"edge": False}

        def side_effect(kwargs, browser):
            if kwargs.get("channel") == "msedge" and state["edge"]:
                return browser
            raise Exception("not found")

        chain, chromium = _chain_with_launch(side_effect)
        clock = [1000.0]
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain), \
             patch("execution.scrapers.playwright_scraper.time.monotonic", side_effect=lambda: clock[0]):
            assert fetch_html_playwright("https://a") is None
            state["edge"] = True
            clock[0] += playwright_scraper.RETRY_DETECTION_AFTER - 1
            assert fetch_html_playwright("https://b") is None  # ainda no intervalo de espera
            clock[0] += 2
            assert fetch_html_playwright("https://c") == "<html>ok</html>"

        assert _channels_tried(chromium) == ["msedge", "chrome", None, "msedge"]
        assert playwright_scraper.browser_in_use() == "Microsoft Edge"

    def test_remembered_browser_that_stops_working_is_detected_again(self):
        state = {"edge": True}

        def side_effect(kwargs, browser):
            channel = kwargs.get("channel")
            if channel == "msedge" and state["edge"]:
                return browser
            if channel == "chrome":
                return browser
            raise Exception("not found")

        chain, chromium = _chain_with_launch(side_effect)
        with patch("execution.scrapers.playwright_scraper.sync_playwright", return_value=chain):
            assert fetch_html_playwright("https://a") == "<html>ok</html>"
            state["edge"] = False  # ex: Edge desinstalado com o app aberto
            assert fetch_html_playwright("https://b") is None
            assert fetch_html_playwright("https://c") == "<html>ok</html>"

        assert _channels_tried(chromium) == ["msedge", "msedge", "msedge", "chrome"]
        assert playwright_scraper.browser_in_use() == "Google Chrome"
