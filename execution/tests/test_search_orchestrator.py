"""
Unit tests for the price-range filter in execution/search_orchestrator.py.

Covers: items below min_price / above max_price are discarded, items with
price=None are discarded once a filter is active but kept when no filter is
set, relevance filtering still applies alongside the price filter, and
run_product_search threads min_price/max_price through to persistence.
"""

from unittest.mock import patch, MagicMock

from execution.search_orchestrator import _filter_and_sort, _filter_by_price, run_product_search
from execution.search_scrapers.errors import StoreBlockedError


def _result(title="Produto Teste", price=None, store="amazon"):
    return {"title": title, "price": price, "store": store, "product_url": "https://example.com"}


class TestFilterByPrice:
    def test_no_bounds_returns_all_results_unchanged(self):
        results = [_result(price=10.0), _result(price=None), _result(price=500.0)]
        assert _filter_by_price(results, None, None) == results

    def test_discards_items_below_min_price(self):
        results = [_result(price=10.0), _result(price=20.0), _result(price=30.0)]
        filtered = _filter_by_price(results, 20.0, None)
        assert [r["price"] for r in filtered] == [20.0, 30.0]

    def test_discards_items_above_max_price(self):
        results = [_result(price=10.0), _result(price=20.0), _result(price=30.0)]
        filtered = _filter_by_price(results, None, 20.0)
        assert [r["price"] for r in filtered] == [10.0, 20.0]

    def test_discards_items_outside_min_max_range(self):
        results = [_result(price=5.0), _result(price=20.0), _result(price=50.0)]
        filtered = _filter_by_price(results, 10.0, 30.0)
        assert [r["price"] for r in filtered] == [20.0]

    def test_discards_unpriced_items_when_filter_is_active(self):
        results = [_result(price=None), _result(price=20.0)]
        filtered = _filter_by_price(results, 10.0, None)
        assert [r["price"] for r in filtered] == [20.0]

    def test_keeps_unpriced_items_when_no_filter_is_active(self):
        results = [_result(price=None), _result(price=20.0)]
        assert _filter_by_price(results, None, None) == results


class TestFilterAndSortWithPrice:
    def test_price_filter_applies_after_relevance_filter(self):
        results = [
            _result(title="iPhone 15 128GB", price=1000.0),
            _result(title="iPhone 15 128GB", price=50.0),
            _result(title="Capinha qualquer", price=30.0),  # irrelevant, dropped regardless
        ]
        filtered = _filter_and_sort("iPhone 15 128GB", results, min_price=100.0)
        assert len(filtered) == 1
        assert filtered[0]["price"] == 1000.0

    def test_no_price_bounds_keeps_relevance_filtered_results_unpriced_included(self):
        results = [
            _result(title="Echo Dot", price=None),
            _result(title="Echo Dot", price=349.0),
        ]
        filtered = _filter_and_sort("Echo Dot", results)
        assert len(filtered) == 2


class TestRunProductSearchThreadsPriceBounds:
    def test_min_max_price_passed_to_filter_and_sort(self):
        with patch("execution.search_orchestrator.SEARCH_FUNCTIONS", []), \
             patch("execution.search_orchestrator._filter_and_sort", return_value=[]) as mock_filter, \
             patch("execution.search_orchestrator.save_search_results", return_value=0):
            run_product_search("echo dot", min_price=20.0, max_price=100.0, search_id="sid-1")

        mock_filter.assert_called_once_with("echo dot", [], 20.0, 100.0)


def _make_search_fn(module_name: str, *, raises: Exception | None = None, results=None):
    """Builds a fake search function mimicking search_amazon/search_mercadolivre's
    shape (a plain function whose __module__ names the store)."""
    def fn(query, max_results=10):
        if raises:
            raise raises
        return results or []
    fn.__module__ = f"execution.search_scrapers.{module_name}"
    return fn


class TestRunProductSearchHandlesStoreBlocks:
    def test_blocked_store_does_not_stop_other_stores(self):
        blocked_fn = _make_search_fn("mercadolivre_search", raises=StoreBlockedError("login_wall"))
        ok_fn = _make_search_fn(
            "amazon_search",
            results=[{"title": "iPhone 15", "price": 100.0, "store": "amazon", "product_url": "https://x"}],
        )

        with patch("execution.search_orchestrator.SEARCH_FUNCTIONS", [blocked_fn, ok_fn]), \
             patch("execution.search_orchestrator.set_search_warnings") as mock_set_warnings, \
             patch("execution.search_orchestrator.save_search_results", return_value=1) as mock_save:
            run_product_search("iPhone 15", search_id="sid-2")

        mock_set_warnings.assert_called_once_with("sid-2", {"mercadolivre": "login_wall"})
        saved_results = mock_save.call_args[0][2]
        assert len(saved_results) == 1
        assert saved_results[0]["store"] == "amazon"

    def test_no_warnings_persisted_when_nothing_is_blocked(self):
        ok_fn = _make_search_fn("amazon_search", results=[])

        with patch("execution.search_orchestrator.SEARCH_FUNCTIONS", [ok_fn]), \
             patch("execution.search_orchestrator.set_search_warnings") as mock_set_warnings, \
             patch("execution.search_orchestrator.save_search_results", return_value=0):
            run_product_search("echo dot", search_id="sid-3")

        mock_set_warnings.assert_not_called()
