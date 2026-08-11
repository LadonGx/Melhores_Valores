"""
Unit tests for web_server._compute_promotions.

Uses MagicMock to simulate the Prisma Product/PriceHistory objects returned by
get_products_with_history — same style as _make_product in test_worker_pipeline.py.
"""

from unittest.mock import MagicMock

from execution.web_server import _compute_promotions


def _make_history_entry(price, in_stock=True):
    h = MagicMock()
    h.price = price
    h.inStock = in_stock
    return h


def _make_product(product_id="prod-1", history=None):
    p = MagicMock()
    p.id = product_id
    p.url = "https://example.com/produto"
    p.name = "Produto Teste"
    p.store = "amazon"
    p.imageUrl = None
    p.history = history or []
    return p


class TestComputePromotions:
    def test_out_of_stock_latest_entry_is_excluded_even_with_low_historical_price(self):
        """Regressão: checagem mais recente confirmada fora de estoque (price=None) não
        deve fazer o produto aparecer em promoções, mesmo que um preço antigo no
        histórico seja baixo o suficiente para "ganhar" do restante do histórico."""
        product = _make_product(history=[
            _make_history_entry(None, in_stock=False),  # mais recente: fora de estoque
            _make_history_entry(50.0),                  # preço antigo, seria "vencedor"
            _make_history_entry(200.0),
            _make_history_entry(180.0),
        ])
        promotions = _compute_promotions([product])
        assert promotions == []

    def test_active_product_below_historical_low_appears_as_promotion(self):
        product = _make_product(history=[
            _make_history_entry(80.0),   # atual: menor que o histórico anterior
            _make_history_entry(200.0),
            _make_history_entry(180.0),
        ])
        promotions = _compute_promotions([product])
        assert len(promotions) == 1
        assert promotions[0]["current_price"] == 80.0
        assert promotions[0]["previous_lowest_price"] == 180.0
        assert promotions[0]["savings"] == 100.0
        assert promotions[0]["in_stock"] is True

    def test_current_price_not_below_historical_low_is_not_a_promotion(self):
        product = _make_product(history=[
            _make_history_entry(190.0),
            _make_history_entry(200.0),
            _make_history_entry(180.0),  # menor preço histórico já foi esse
        ])
        promotions = _compute_promotions([product])
        assert promotions == []

    def test_single_history_entry_has_nothing_to_compare_against(self):
        product = _make_product(history=[_make_history_entry(100.0)])
        promotions = _compute_promotions([product])
        assert promotions == []

    def test_product_without_history_is_skipped(self):
        product = _make_product(history=[])
        promotions = _compute_promotions([product])
        assert promotions == []

    def test_previous_out_of_stock_entries_are_ignored_in_comparison(self):
        """Entradas antigas com price=None (fora de estoque no passado) não devem
        contar como candidatas a 'menor preço anterior', só são ignoradas."""
        product = _make_product(history=[
            _make_history_entry(80.0),
            _make_history_entry(None, in_stock=False),
            _make_history_entry(180.0),
        ])
        promotions = _compute_promotions([product])
        assert len(promotions) == 1
        assert promotions[0]["previous_lowest_price"] == 180.0
