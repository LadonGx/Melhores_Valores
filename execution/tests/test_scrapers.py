"""
Unit tests for the two fetch strategies used by the scraping cascade.

Contract under test: `fetch_html_simple` and `fetch_html_playwright` must
NEVER raise — any network/browser failure is caught internally and turned
into a `None` return, so `scraping_orchestrator.py` can escalate to the next
level of the cascade. All network/browser calls are mocked; no test touches
the real internet.
"""

from unittest.mock import patch, MagicMock

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
