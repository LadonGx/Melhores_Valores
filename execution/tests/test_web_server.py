"""
Unit tests for web_server (_compute_promotions, GET /products, POST /product/{id}/refresh).

Uses MagicMock to simulate the Prisma Product/PriceHistory objects returned by
get_products_with_history — same style as _make_product in test_worker_pipeline.py.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from execution.web_server import _compute_promotions, list_products, refresh_product_price


def _make_history_entry(price, in_stock=True, seller_type=None, seller_name=None):
    h = MagicMock()
    h.price = price
    h.inStock = in_stock
    h.sellerType = seller_type
    h.sellerName = seller_name
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


class TestComputePromotionsThirdParty:
    """Preço de terceiro fica no histórico, mas não vira referência de promoção."""

    def test_amazon_back_after_pricier_third_party_is_not_a_promotion(self):
        product = _make_product(history=[
            _make_history_entry(70.0, seller_type="amazon"),          # Amazon voltou
            _make_history_entry(110.0, seller_type="third_party_from"),
            _make_history_entry(70.0, seller_type="amazon"),
        ])
        assert _compute_promotions([product]) == []

    def test_third_party_current_price_is_not_a_promotion_when_amazon_exists(self):
        product = _make_product(history=[
            _make_history_entry(60.0, seller_type="third_party", seller_name="Sebo X"),
            _make_history_entry(70.0, seller_type="amazon"),
        ])
        assert _compute_promotions([product]) == []

    def test_amazon_price_below_own_history_ignores_cheaper_third_party(self):
        product = _make_product(history=[
            _make_history_entry(65.0, seller_type="amazon"),
            _make_history_entry(50.0, seller_type="third_party", seller_name="Sebo X"),
            _make_history_entry(70.0),  # registro antigo, vendedor não identificado
        ])
        [promo] = _compute_promotions([product])
        assert promo["previous_lowest_price"] == 70.0

    def test_listing_only_ever_sold_by_third_parties_uses_their_prices(self):
        product = _make_product(history=[
            _make_history_entry(80.0, seller_type="third_party_from"),
            _make_history_entry(95.0, seller_type="third_party_from"),
        ])
        [promo] = _compute_promotions([product])
        assert promo["previous_lowest_price"] == 95.0


# ─── GET /products: última verificação ────────────────────────────────────────

def _make_listed_product(history=None, **last_check):
    """Produto como vem de get_all_products (history com no máximo 1 item)."""
    p = _make_product(history=history)
    p.status = "active"
    p.createdAt = datetime(2026, 11, 1, tzinfo=timezone.utc)
    p.updatedAt = datetime(2026, 11, 1, tzinfo=timezone.utc)
    p.lastCheckedAt = last_check.get("lastCheckedAt")
    p.lastAttemptAt = last_check.get("lastAttemptAt")
    p.lastCheckStatus = last_check.get("lastCheckStatus")
    p.lastCheckError = last_check.get("lastCheckError")
    return p


def _history_entry_at(scraped_at, price=100.0):
    h = _make_history_entry(price)
    h.scrapedAt = scraped_at
    return h


def _list_products(products):
    with patch("execution.web_server.get_all_products", return_value=products):
        return asyncio.run(list_products())["products"]


class TestListProductsLastCheck:
    def test_last_checked_uses_last_checked_at_not_history(self):
        """O histórico é deduplicado: o último registro pode ter 15 h, mas a
        última checagem real foi há 1 h."""
        old_entry = _history_entry_at(datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc))
        product = _make_listed_product(
            history=[old_entry],
            lastCheckedAt=datetime(2026, 11, 11, 11, 0, tzinfo=timezone.utc),
            lastAttemptAt=datetime(2026, 11, 11, 11, 0, tzinfo=timezone.utc),
            lastCheckStatus="ok",
        )
        [item] = _list_products([product])
        assert item["last_checked"] == "2026-11-11T11:00:00+00:00"

    def test_last_checked_falls_back_to_history_when_null(self):
        entry = _history_entry_at(datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc))
        [item] = _list_products([_make_listed_product(history=[entry])])
        assert item["last_checked"] == "2026-11-10T21:00:00+00:00"

    def test_last_checked_is_null_without_check_nor_history(self):
        [item] = _list_products([_make_listed_product(history=[])])
        assert item["last_checked"] is None
        assert item["last_attempt_at"] is None
        assert item["last_check_status"] is None
        assert item["last_check_error"] is None

    def test_exposes_attempt_status_and_error(self):
        product = _make_listed_product(
            history=[],
            lastCheckedAt=datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc),
            lastAttemptAt=datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc),
            lastCheckStatus="blocked",
            lastCheckError="captcha",
        )
        [item] = _list_products([product])
        assert item["last_checked"] == "2026-11-11T06:00:00+00:00"
        assert item["last_attempt_at"] == "2026-11-11T12:00:00+00:00"
        assert item["last_check_status"] == "blocked"
        assert item["last_check_error"] == "captcha"

    def test_exposes_seller_of_current_price(self):
        entry = _history_entry_at(datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc), price=180.64)
        entry.sellerType = "third_party"
        entry.sellerName = "JS Digital BR"
        [item] = _list_products([_make_listed_product(history=[entry])])
        assert item["seller_type"] == "third_party"
        assert item["seller_name"] == "JS Digital BR"


# ─── POST /product/{id}/refresh ───────────────────────────────────────────────

class TestRefreshNoOffer:
    def test_no_offer_result_is_reported_as_error(self):
        product = _make_product()
        pipeline_result = {
            "status": "no_offer", "url": product.url, "store": "amazon",
            "reason": "Anúncio sem oferta principal.",
        }
        with patch("execution.web_server.get_product_by_id", return_value=product), \
             patch("execution.web_server.run_price_pipeline", return_value=pipeline_result):
            response = asyncio.run(refresh_product_price("prod-1"))
        assert response == {
            "status": "error",
            "reason": "no_offer",
            "detail": "O anúncio está sem oferta principal no momento (só outros vendedores, sem preço exibido).",
        }

    def test_pipeline_exception_keeps_exception_response(self):
        product = _make_product()
        with patch("execution.web_server.get_product_by_id", return_value=product), \
             patch("execution.web_server.run_price_pipeline", side_effect=RuntimeError("boom")):
            response = asyncio.run(refresh_product_price("prod-1"))
        assert response["status"] == "error"
        assert response["reason"] == "exception"
