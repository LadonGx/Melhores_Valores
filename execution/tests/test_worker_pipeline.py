"""
Unit tests for worker_tasks.run_price_pipeline.

All DB and scraping calls are mocked so these run without Docker.
"""

from unittest.mock import patch, MagicMock, call
import pytest

from execution.worker_tasks import run_price_pipeline


def _make_product(product_id="prod-1", name="Produto Teste"):
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.imageUrl = None
    return p


# ─── Helpers ──────────────────────────────────────────────────────────────────

MOCK_PATCHES = {
    "scrape": "execution.worker_tasks.scrape_product",
    "cache_get": "execution.worker_tasks.get_cached_price",
    "cache_set": "execution.worker_tasks.set_cached_price",
    "get_or_create": "execution.worker_tasks.get_or_create_product",
    "add_history": "execution.worker_tasks.add_price_history",
    "last_price": "execution.worker_tasks.get_last_valid_price_for_url",
    # Imported as `is_garbage_name as _is_garbage_name` in worker_tasks
    "is_garbage": "execution.worker_tasks._is_garbage_name",
    "normalize_store": "execution.worker_tasks.normalize_store",
}


# ─── Cache hit path ───────────────────────────────────────────────────────────

class TestCacheHit:
    def test_cache_hit_returns_cached_price_without_scraping(self):
        product = _make_product()
        with patch(MOCK_PATCHES["cache_get"], return_value={"price": 199.90, "name": "Produto Teste"}), \
             patch(MOCK_PATCHES["scrape"]) as mock_scrape, \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "ok"
            assert result["price"] == 199.90
            assert result["source"] == "cache"
            mock_scrape.assert_not_called()

    def test_cache_skip_forces_scraping(self):
        product = _make_product()
        scrape_result = {"price": 189.90, "confidence_score": 0.92, "in_stock": True, "name": "Produto"}
        with patch(MOCK_PATCHES["cache_get"]) as mock_cache, \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]), \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon", skip_cache=True)
            assert result["status"] == "ok"
            mock_cache.assert_not_called()


# ─── Successful scrape path ───────────────────────────────────────────────────

class TestSuccessfulScrape:
    def test_scrape_success_saves_price_history(self):
        product = _make_product()
        scrape_result = {
            "price": 199.90,
            "name": "Produto Teste",
            "image_url": None,
            "in_stock": True,
            "confidence_score": 0.92,
        }
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product) as mock_create, \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "ok"
            assert result["price"] == 199.90
            assert result["in_stock"] is True
            mock_history.assert_called_once_with(product_id="prod-1", price=199.90, in_stock=True)

    def test_scrape_success_updates_cache(self):
        product = _make_product()
        scrape_result = {"price": 99.0, "name": "Produto", "image_url": None, "in_stock": True, "confidence_score": 0.9}
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]), \
             patch(MOCK_PATCHES["cache_set"]) as mock_cache_set, \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            mock_cache_set.assert_called_once()


# ─── Failure and out-of-stock paths ───────────────────────────────────────────

class TestFailureAndOutOfStock:
    def test_cascade_failure_records_history_entry(self):
        product = _make_product()
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=None), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon", fallback_name="Produto Teste")
            assert result["status"] == "error"
            mock_history.assert_called_once_with(product_id="prod-1", price=None, in_stock=False)

    def test_out_of_stock_confirmed_records_history(self):
        product = _make_product()
        scrape_result = {"price": None, "in_stock": False, "confidence_score": 0.75, "name": "Produto", "image_url": None}
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "out_of_stock"
            mock_history.assert_called_once_with(product_id="prod-1", price=None, in_stock=False)

    def test_out_of_stock_confirmed_does_not_update_cache(self):
        product = _make_product()
        scrape_result = {"price": None, "in_stock": False, "confidence_score": 0.75, "name": "Produto", "image_url": None}
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]), \
             patch(MOCK_PATCHES["cache_set"]) as mock_cache_set, \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            mock_cache_set.assert_not_called()

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            run_price_pipeline("", "amazon")


# ─── Sanity check path ────────────────────────────────────────────────────────

class TestSanityCheck:
    def test_large_price_jump_with_low_confidence_is_blocked(self):
        product = _make_product()
        scrape_result = {
            "price": 9999.0,  # 50x the last known price
            "name": "Produto",
            "image_url": None,
            "in_stock": True,
            "confidence_score": 0.60,  # below 0.75 threshold
        }
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["last_price"], return_value=199.90), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "error"
            mock_history.assert_not_called()

    def test_large_price_jump_with_high_confidence_is_saved(self):
        product = _make_product()
        scrape_result = {
            "price": 9999.0,
            "name": "Produto",
            "image_url": None,
            "in_stock": True,
            "confidence_score": 0.92,  # above 0.75 threshold
        }
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=scrape_result), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=199.90), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "ok"
            mock_history.assert_called_once()
