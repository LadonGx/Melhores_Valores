"""
Unit tests for store adapters (amazon, mercadolivre).

Tests cover: normal extraction, block detection, out-of-stock detection,
price parsing edge cases, and confirmed-unavailable signal propagation.
"""

from pathlib import Path

import pytest
from execution.adapters import amazon, mercadolivre, parse_product_data

AMAZON_FIXTURES = Path(__file__).parent / "fixtures" / "amazon"


def _amazon_fixture(asin: str) -> dict:
    """Extrai o HTML real (página deslogada) salvo em fixtures/amazon/<ASIN>.html."""
    html = (AMAZON_FIXTURES / f"{asin}.html").read_text(encoding="utf-8")
    result = amazon.extract_from_html(html)
    assert result is not None
    return result


# ─── HTML Fixtures ───────────────────────────────────────────────────────────

AMAZON_NORMAL = """
<html><head><title>Livro Exemplo - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro de Programação Python</span>
  <div id="corePrice_feature_div">
    <span class="a-price">
      <span class="a-offscreen">R$ 199,90</span>
    </span>
  </div>
  <div id="availability"><span>Em estoque.</span></div>
</body></html>
"""

AMAZON_OUT_OF_STOCK_NO_PRICE = """
<html><head><title>Livro Exemplo - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro de Programação Python</span>
  <div id="availability"><span>Indisponível.</span></div>
</body></html>
"""

AMAZON_OUT_OF_STOCK_WITH_PRICE = """
<html><head><title>Livro Exemplo - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro de Programação Python</span>
  <div id="corePrice_feature_div">
    <span class="a-price">
      <span class="a-offscreen">R$ 199,90</span>
    </span>
  </div>
  <div id="availability"><span>Fora de estoque.</span></div>
</body></html>
"""

AMAZON_CAPTCHA = """
<html><head><title>Robot Check</title></head>
<body>Enter the characters you see below, prove you're not a robot</body>
</html>
"""

AMAZON_NO_PRICE_NO_STOCK_SIGNAL = """
<html><head><title>Livro - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro X</span>
</body></html>
"""

AMAZON_STRIKETHROUGH_PRICE = """
<html><head><title>Produto - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Produto com desconto</span>
  <div id="corePrice_feature_div">
    <span class="a-price a-text-strike">
      <span class="a-offscreen">R$ 299,90</span>
    </span>
    <span class="a-price">
      <span class="a-offscreen">R$ 199,90</span>
    </span>
  </div>
  <div id="availability"><span>Em estoque.</span></div>
</body></html>
"""

# Sale price via priceToPay + original shown via a-text-price (NOT a-text-strike)
AMAZON_SALE_PRICE_PAY_CLASS = """
<html><head><title>Livro em Oferta - Amazon.com.br</title></head>
<body>
  <span id="productTitle">O Caminho dos Reis</span>
  <div id="corePrice_feature_div">
    <span class="a-price a-text-price">
      <span class="a-offscreen">R$ 199,90</span>
    </span>
    <span class="a-price priceToPay">
      <span class="a-offscreen">R$ 103,79</span>
    </span>
  </div>
  <div id="availability"><span>Em estoque.</span></div>
</body></html>
"""

# apexPriceToPay variant (Lightning Deals layout)
AMAZON_APEX_PRICE = """
<html><head><title>Livro - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro Teste</span>
  <div id="apex_desktop_newAccordionRow">
    <span class="a-price apexPriceToPay">
      <span class="a-offscreen">R$ 89,90</span>
    </span>
  </div>
  <div id="availability"><span>Em estoque.</span></div>
</body></html>
"""

# Anúncio sem caixa de compra: o único span.a-price da página é de um carrossel
AMAZON_CAROUSEL_ONLY_PRICE = """
<html><head><title>Livro - Amazon.com.br</title></head>
<body>
  <span id="productTitle">Livro sem oferta</span>
  <div id="buybox">
    <span id="buybox-see-all-buying-choices"><a href="#">Ver todas as opções de compra</a></span>
  </div>
  <div id="sp_detail">
    <span class="a-price"><span class="a-offscreen">R$ 52,40</span></span>
  </div>
  <div id="similarities_feature_div">
    <span class="a-price">
      <span class="a-price-whole">37<span class="a-price-decimal">,</span></span>
      <span class="a-price-fraction">31</span>
    </span>
  </div>
</body></html>
"""

MERCADOLIVRE_NORMAL = """
<html><head><title>Produto - Mercado Livre</title></head>
<body>
  <h1 class="ui-pdp-title">Livro Python na Prática</h1>
  <div class="ui-pdp-price__second-line">
    <span class="andes-money-amount" aria-label="199 reais com 90 centavos">R$ 199,90</span>
  </div>
</body></html>
"""

MERCADOLIVRE_OUT_OF_STOCK_CSS = """
<html><head><title>Produto - Mercado Livre</title></head>
<body>
  <h1 class="ui-pdp-title">Livro Python na Prática</h1>
  <div class="ui-pdp-buybox--unavailable">
    <span>Produto indisponível</span>
  </div>
</body></html>
"""

MERCADOLIVRE_BLOCKED = """
<html><head><title>Acesse sua conta</title></head>
<body>Faça seu login para continuar</body>
</html>
"""

MERCADOLIVRE_NO_PRICE = """
<html><head><title>Produto - Mercado Livre</title></head>
<body>
  <h1 class="ui-pdp-title">Livro Python</h1>
</body></html>
"""

# Reproduz o banner real de indisponibilidade do ML (confirmado via HTML real capturado
# pelo usuário) — usa .ui-pdp-shipping-message__text, fora dos seletores antigos.
MERCADOLIVRE_OUT_OF_STOCK_SHIPPING_MESSAGE = """
<html><head><title>Produto - Mercado Livre</title></head>
<body>
  <h1 class="ui-pdp-title">Livro O Caminho Dos Reis</h1>
  <div class="ui-pdp-message ui-pdp-shipping-message mt-24 mb-16 andes-message andes-message--caution andes-message--quiet">
    <div class="andes-message__content andes-message__content--untitled">
      <div class="andes-message__text">
        <div class="ui-pdp-shipping-message__text">Este produto está indisponível no momento.</div>
      </div>
    </div>
  </div>
</body></html>
"""

# Página sem o banner CSS, mas com o JSON-LD schema.org/Product confirmando OutOfStock.
MERCADOLIVRE_OUT_OF_STOCK_JSON_LD = """
<html><head><title>Produto - Mercado Livre</title></head>
<body>
  <h1 class="ui-pdp-title">Livro O Caminho Dos Reis</h1>
  <script type="application/ld+json">
  {"name": "Livro O Caminho Dos Reis", "offers": {"@type": "Offer", "price": 0, "availability": "https://schema.org/OutOfStock"}, "@type": "Product"}
  </script>
</body></html>
"""

# ─── Amazon Tests ─────────────────────────────────────────────────────────────

class TestAmazonAdapter:
    def test_normal_extraction(self):
        result = amazon.extract_from_html(AMAZON_NORMAL)
        assert result is not None
        assert result["price"] == 199.90
        assert result["in_stock"] is True
        assert result["name"] == "Livro de Programação Python"
        assert result["confidence_score"] >= 0.55
        assert result["block_category"] is None

    def test_captcha_returns_block_category(self):
        result = amazon.extract_from_html(AMAZON_CAPTCHA)
        assert result is not None
        assert result["block_category"] == "captcha"
        assert result["price"] is None

    def test_out_of_stock_no_price_returns_in_stock_false(self):
        result = amazon.extract_from_html(AMAZON_OUT_OF_STOCK_NO_PRICE)
        assert result is not None
        assert result["in_stock"] is False
        assert result["price"] is None
        assert result["confidence_score"] >= 0.55

    def test_out_of_stock_with_price_records_price(self):
        result = amazon.extract_from_html(AMAZON_OUT_OF_STOCK_WITH_PRICE)
        assert result is not None
        assert result["price"] == 199.90
        assert result["in_stock"] is False

    def test_no_price_no_stock_signal_returns_none(self):
        """Sem preço e sem sinal de "sem oferta principal": o bloco de preço pode só estar
        faltando neste HTML — devolve None para a cascata escalar, como antes."""
        result = amazon.extract_from_html(AMAZON_NO_PRICE_NO_STOCK_SIGNAL)
        assert result is None

    def test_see_all_buying_choices_without_price_returns_no_offer(self):
        """Só "Ver todas as opções de compra", sem preço nem "a partir de": sem oferta
        principal (não é falha, nem fora de estoque) — a cascata para aqui, sem Firecrawl."""
        result = amazon.extract_from_html(AMAZON_CAROUSEL_ONLY_PRICE)
        assert result is not None
        assert result["price"] is None
        assert result["in_stock"] is True
        assert result["offer_type"] == "none"
        assert result["confidence_score"] == 0.6
        assert result["block_category"] is None

    def test_out_of_stock_no_price_is_not_reported_as_no_offer(self):
        """Fora de estoque confirmado não leva offer_type "none": o pipeline checaria
        "none" antes do estoque e gravaria no_offer em vez de out_of_stock."""
        result = amazon.extract_from_html(AMAZON_OUT_OF_STOCK_NO_PRICE)
        assert result["in_stock"] is False
        assert "offer_type" not in result

    def test_prices_outside_product_price_areas_are_ignored(self):
        """Carrossel de recomendações/patrocinados nunca é o preço do produto."""
        result = amazon.extract_from_html(AMAZON_CAROUSEL_ONLY_PRICE)
        assert result is not None
        assert result["price"] is None
        assert result["offer_type"] == "none"

    def test_non_product_page_without_title_returns_none(self):
        """Sem título nem preço não dá para afirmar que é um anúncio: deixa a cascata escalar."""
        result = amazon.extract_from_html("<html><head><title>Amazon.com.br</title></head><body>ok</body></html>")
        assert result is None

    def test_strikethrough_price_skipped(self):
        result = amazon.extract_from_html(AMAZON_STRIKETHROUGH_PRICE)
        assert result is not None
        assert result["price"] == 199.90  # discounted price, not the strikethrough

    def test_sale_price_via_price_to_pay_class(self):
        """priceToPay class must win over a-text-price original (R$199,90 vs R$103,79)."""
        result = amazon.extract_from_html(AMAZON_SALE_PRICE_PAY_CLASS)
        assert result is not None
        assert result["price"] == 103.79, f"Expected 103.79 (sale price) but got {result['price']}"
        assert result["confidence_score"] >= 0.95

    def test_apex_price_to_pay(self):
        """apexPriceToPay (Lightning Deals layout) should be detected."""
        result = amazon.extract_from_html(AMAZON_APEX_PRICE)
        assert result is not None
        assert result["price"] == 89.90
        assert result["confidence_score"] >= 0.95

    def test_a_text_price_original_is_skipped(self):
        """a-text-price ('was' price in grey) must not be returned when sale price exists."""
        result = amazon.extract_from_html(AMAZON_SALE_PRICE_PAY_CLASS)
        assert result is not None
        assert result["price"] != 199.90, "Returned original price instead of sale price"

    def test_empty_html_returns_none(self):
        result = amazon.extract_from_html("<html></html>")
        assert result is None


class TestAmazonRealPages:
    """HTML real de páginas de produto da Amazon BR (execution/tests/fixtures/amazon)."""

    def test_no_main_offer_never_returns_carousel_price(self):
        """6525954525: a Amazon não vende direto, só outros vendedores ("Capa Comum a partir
        de R$ 78,90"). Os R$ 52,40 / R$ 37,31 são de cards de recomendação da página."""
        result = _amazon_fixture("6525954525")
        assert result["price"] not in (52.40, 37.31)
        assert result["price"] == 78.90
        assert result["offer_type"] == "third_party_from"
        assert result["confidence_score"] == 0.6
        assert result["in_stock"] is True

    def test_kindle_returns_selected_format_price_not_recommendation(self):
        """B0FYGGWCHR (Kindle): R$ 84,71 no botão selecionado; R$ 92,90 era de um CardInstance."""
        result = _amazon_fixture("B0FYGGWCHR")
        assert result["price"] != 92.90
        assert result["price"] == 84.71
        assert result["offer_type"] == "main"
        assert result["confidence_score"] >= 0.72

    @pytest.mark.parametrize(
        "asin, expected",
        [
            ("6525948150", 59.18),   # preço no botão de formato selecionado
            ("B0DKLNNYY4", 639.00),  # #corePrice_feature_div
            ("6501370515", 88.49),   # span.priceToPay
        ],
    )
    def test_listings_with_main_offer_keep_their_price(self, asin, expected):
        result = _amazon_fixture(asin)
        assert result["price"] == expected
        assert result["offer_type"] == "main"
        assert result["confidence_score"] >= 0.72
        assert result["in_stock"] is True

    def test_promotional_visible_price_wins_over_regular_format_price(self):
        """6525946328: o preço em destaque é R$ 67,45 (5% off à vista no Pix/NuPay); o botão
        do formato selecionado mostra o preço normal, R$ 71,00. O projeto registra sempre o
        preço com promoção."""
        result = _amazon_fixture("6525946328")
        assert result["price"] == 67.45
        assert result["offer_type"] == "main"


# ─── MercadoLivre Tests ───────────────────────────────────────────────────────

class TestMercadoLivreAdapter:
    def test_normal_extraction(self):
        result = mercadolivre.extract_from_html(MERCADOLIVRE_NORMAL)
        assert result is not None
        assert result["price"] == 199.90
        assert result["in_stock"] is True
        assert result["name"] == "Livro Python na Prática"
        assert result["block_category"] is None

    def test_out_of_stock_css_class(self):
        result = mercadolivre.extract_from_html(MERCADOLIVRE_OUT_OF_STOCK_CSS)
        assert result is not None
        assert result["in_stock"] is False
        assert result["price"] is None
        assert result["confidence_score"] >= 0.55

    def test_login_wall_returns_block_category(self):
        result = mercadolivre.extract_from_html(MERCADOLIVRE_BLOCKED)
        assert result is not None
        assert result["block_category"] == "login_wall"
        assert result["price"] is None

    def test_no_price_no_stock_signal_returns_none(self):
        result = mercadolivre.extract_from_html(MERCADOLIVRE_NO_PRICE)
        assert result is None

    def test_empty_html_returns_none(self):
        result = mercadolivre.extract_from_html("<html></html>")
        assert result is None

    def test_aria_label_price_parsing(self):
        result = mercadolivre.extract_from_html(MERCADOLIVRE_NORMAL)
        assert result is not None
        assert result["price"] == 199.90

    def test_out_of_stock_shipping_message_banner(self):
        """Banner real do ML (.ui-pdp-shipping-message__text) — não usa os seletores antigos."""
        result = mercadolivre.extract_from_html(MERCADOLIVRE_OUT_OF_STOCK_SHIPPING_MESSAGE)
        assert result is not None
        assert result["in_stock"] is False
        assert result["price"] is None
        assert result["confidence_score"] >= 0.55

    def test_out_of_stock_via_json_ld(self):
        """Fallback estrutural via JSON-LD schema.org/Product quando não há banner CSS."""
        result = mercadolivre.extract_from_html(MERCADOLIVRE_OUT_OF_STOCK_JSON_LD)
        assert result is not None
        assert result["in_stock"] is False
        assert result["price"] is None
        assert result["confidence_score"] >= 0.55


# ─── Firecrawl path: extract_in_stock / parse_product_data ───────────────────

class TestFirecrawlInStockExtraction:
    """Regressão: o caminho do Firecrawl (usado quando httpx/Playwright são bloqueados)
    precisa propagar 'in_stock' — antes desse fix, ele nunca setava essa chave."""

    @pytest.mark.parametrize("adapter", [amazon, mercadolivre])
    def test_extract_in_stock_false_when_unavailable(self, adapter):
        payload = {"data": {"metadata": {"title": "Produto", "price": 0, "available": False}}}
        assert adapter.extract_in_stock(payload) is False

    @pytest.mark.parametrize("adapter", [amazon, mercadolivre])
    def test_extract_in_stock_defaults_true_when_missing(self, adapter):
        payload = {"data": {"metadata": {"title": "Produto", "price": 199.90}}}
        assert adapter.extract_in_stock(payload) is True

    def test_parse_product_data_propagates_in_stock_false(self):
        payload = {"data": {"metadata": {"title": "Livro X", "price": 0, "available": False}}}
        result = parse_product_data("mercadolivre", payload)
        assert result["in_stock"] is False
        assert result["price"] == 0.0

    def test_parse_product_data_defaults_in_stock_true(self):
        payload = {"data": {"metadata": {"title": "Livro X", "price": 199.90}}}
        result = parse_product_data("mercadolivre", payload)
        assert result["in_stock"] is True


# ─── Price parsing edge cases ─────────────────────────────────────────────────

class TestPriceParsing:
    def test_amazon_brl_format(self):
        val = amazon._parse_price_text("R$ 1.299,00")
        assert val == 1299.0

    def test_amazon_simple_format(self):
        val = amazon._parse_price_text("199,90")
        assert val == 199.90

    def test_amazon_zero_returns_none(self):
        val = amazon._parse_price_text("R$ 0,00")
        assert val is None

    def test_amazon_garbage_returns_none(self):
        val = amazon._parse_price_text("indisponível")
        assert val is None
