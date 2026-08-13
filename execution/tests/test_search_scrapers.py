"""
Unit tests for store search-page scrapers (amazon_search, mercadolivre_search).

Tests cover: normal extraction from fixture HTML, malformed cards being
skipped without breaking the rest, BRL price parsing, and graceful `[]`
fallback when the underlying fetch fails. No test touches the real network —
httpx / fetch_html_playwright are always mocked.
"""

from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup

from execution.search_scrapers import amazon_search, mercadolivre_search


# ─── HTML Fixtures ───────────────────────────────────────────────────────────

AMAZON_SEARCH_RESULTS = """
<html><body>
  <div data-component-type="s-search-result">
    <h2><span data-cy="title-recipe"><span>Echo Dot 5ª Geração</span></span></h2>
    <a class="a-link-normal" href="/dp/B09B8V1LZ3">
      <img class="s-image" src="https://img.example/echo.jpg">
    </a>
    <span class="a-price"><span class="a-offscreen">R$ 349,00</span></span>
    <span class="a-icon-alt">4,7 de 5 estrelas</span>
    <span class="a-size-base s-underline-text">1.234</span>
  </div>
  <div data-component-type="s-search-result">
    <!-- Malformed card: no title, no link -- must be skipped, not crash the rest -->
    <span class="a-price"><span class="a-offscreen">R$ 99,00</span></span>
  </div>
</body></html>
"""

ML_SEARCH_RESULTS = """
<html><body>
  <li class="ui-search-layout__item">
    <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-123">Notebook Gamer 16GB</a>
    <img class="poly-component__picture" data-src="https://img.example/notebook.jpg">
    <span class="andes-money-amount" aria-label="107 reais con 58 centavos">R$107,58</span>
    <span class="poly-reviews__rating">4,5</span>
    <span class="poly-reviews__total">200</span>
  </li>
</body></html>
"""


def _mock_httpx_response(html: str, raises: bool = False):
    mock_response = MagicMock()
    mock_response.text = html
    if raises:
        mock_response.raise_for_status.side_effect = Exception("503 Service Unavailable")
    else:
        mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    return mock_client


# ─── search_amazon ────────────────────────────────────────────────────────

class TestSearchAmazon:
    def test_normal_extraction(self):
        mock_client = _mock_httpx_response(AMAZON_SEARCH_RESULTS)
        with patch("execution.search_scrapers.amazon_search.httpx.Client", return_value=mock_client):
            results = amazon_search.search_amazon("echo dot")

        assert len(results) == 1  # the malformed card is dropped
        item = results[0]
        assert item["store"] == "amazon"
        assert item["title"] == "Echo Dot 5ª Geração"
        assert item["product_url"] == "https://www.amazon.com.br/dp/B09B8V1LZ3"
        assert item["price"] == 349.00
        assert item["currency"] == "BRL"
        assert item["image_url"] == "https://img.example/echo.jpg"
        assert item["rating"] == 4.7
        assert item["review_count"] == 1234

    def test_malformed_card_is_skipped_not_fatal(self):
        mock_client = _mock_httpx_response(AMAZON_SEARCH_RESULTS)
        with patch("execution.search_scrapers.amazon_search.httpx.Client", return_value=mock_client):
            results = amazon_search.search_amazon("echo dot")

        # Only the well-formed card survives; no exception propagated.
        titles = [r["title"] for r in results]
        assert "Echo Dot 5ª Geração" in titles
        assert len(results) == 1

    def test_network_failure_returns_empty_list(self):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Connection refused")

        with patch("execution.search_scrapers.amazon_search.httpx.Client", return_value=mock_client):
            results = amazon_search.search_amazon("echo dot")

        assert results == []

    def test_http_error_status_returns_empty_list(self):
        mock_client = _mock_httpx_response(AMAZON_SEARCH_RESULTS, raises=True)
        with patch("execution.search_scrapers.amazon_search.httpx.Client", return_value=mock_client):
            results = amazon_search.search_amazon("echo dot")

        assert results == []


class TestParseAmazonPrice:
    def test_brl_offscreen_format(self):
        soup = BeautifulSoup(
            '<div><span class="a-price"><span class="a-offscreen">R$ 1.234,56</span></span></div>',
            "lxml",
        )
        assert amazon_search._parse_amazon_price(soup.div) == 1234.56

    def test_fallback_whole_fraction_format(self):
        soup = BeautifulSoup(
            '<div><span class="a-price-whole">199</span><span class="a-price-fraction">90</span></div>',
            "lxml",
        )
        assert amazon_search._parse_amazon_price(soup.div) == 199.90

    def test_no_price_returns_none(self):
        soup = BeautifulSoup("<div></div>", "lxml")
        assert amazon_search._parse_amazon_price(soup.div) is None


# ─── search_mercadolivre ──────────────────────────────────────────────────

ML_LOGIN_WALL_HTML = """
<html><head><title>Mercado Libre</title></head>
<body>Olá! Para continuar, acesse sua conta. Sou novo. Já tenho conta.</body></html>
"""

ML_GENUINELY_EMPTY_HTML = """
<html><head><title>Mercado Livre</title></head>
<body>Não encontramos anúncios para essa busca.</body></html>
"""


class TestSearchMercadoLivre:
    def test_normal_extraction(self):
        with patch(
            "execution.search_scrapers.mercadolivre_search.fetch_html_playwright",
            return_value=ML_SEARCH_RESULTS,
        ):
            results = mercadolivre_search.search_mercadolivre("notebook gamer")

        assert len(results) == 1
        item = results[0]
        assert item["store"] == "mercadolivre"
        assert item["title"] == "Notebook Gamer 16GB"
        assert item["product_url"] == "https://produto.mercadolivre.com.br/MLB-123"
        assert item["price"] == 107.58
        assert item["currency"] == "BRL"
        assert item["image_url"] == "https://img.example/notebook.jpg"
        assert item["rating"] == 4.5
        assert item["review_count"] == 200

    def test_playwright_failure_returns_empty_list(self):
        with patch(
            "execution.search_scrapers.mercadolivre_search.fetch_html_playwright",
            return_value=None,
        ):
            results = mercadolivre_search.search_mercadolivre("notebook gamer")

        assert results == []

    def test_login_wall_is_logged_distinctly_from_genuine_empty_result(self, caplog):
        """A block page and a genuinely empty search both yield []. But the anti-bot
        block must be diagnosable in the logs — not silently identical to '0 resultados'."""
        with caplog.at_level("WARNING", logger="execution.search_scrapers.mercadolivre_search"):
            with patch(
                "execution.search_scrapers.mercadolivre_search.fetch_html_playwright",
                return_value=ML_LOGIN_WALL_HTML,
            ):
                results = mercadolivre_search.search_mercadolivre("notebook gamer")

        assert results == []
        assert any("bloqueado (login_wall)" in r.message for r in caplog.records)

    def test_genuinely_empty_result_does_not_log_a_block_warning(self, caplog):
        with caplog.at_level("WARNING", logger="execution.search_scrapers.mercadolivre_search"):
            with patch(
                "execution.search_scrapers.mercadolivre_search.fetch_html_playwright",
                return_value=ML_GENUINELY_EMPTY_HTML,
            ):
                results = mercadolivre_search.search_mercadolivre("produto inexistente")

        assert results == []
        assert not any("bloqueado" in r.message for r in caplog.records)


class TestParseMlPrice:
    def test_aria_label_format(self):
        soup = BeautifulSoup(
            '<div><span class="andes-money-amount" aria-label="107 reais con 58 centavos">R$107,58</span></div>',
            "lxml",
        )
        assert mercadolivre_search._parse_ml_price(soup.div) == 107.58

    def test_plain_text_format(self):
        soup = BeautifulSoup(
            '<div><span class="andes-money-amount">R$1.299,00</span></div>',
            "lxml",
        )
        assert mercadolivre_search._parse_ml_price(soup.div) == 1299.00

    def test_no_price_returns_none(self):
        soup = BeautifulSoup("<div></div>", "lxml")
        assert mercadolivre_search._parse_ml_price(soup.div) is None
