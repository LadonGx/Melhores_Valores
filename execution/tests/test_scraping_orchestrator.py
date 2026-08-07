"""
Unit tests for scraping_orchestrator.py

Tests cascade logic: level skipping, result acceptance threshold,
out-of-stock early stop, and Firecrawl escalation.
"""

from unittest.mock import patch, MagicMock
import pytest

from execution.scraping_orchestrator import _result_is_acceptable, scrape_product


# ─── _result_is_acceptable ────────────────────────────────────────────────────

class TestResultIsAcceptable:
    def test_none_is_not_acceptable(self):
        assert _result_is_acceptable(None) is False

    def test_empty_dict_is_not_acceptable(self):
        assert _result_is_acceptable({}) is False

    def test_valid_price_high_confidence_is_acceptable(self):
        result = {"price": 199.90, "confidence_score": 0.92, "in_stock": True}
        assert _result_is_acceptable(result) is True

    def test_valid_price_below_threshold_is_not_acceptable(self):
        result = {"price": 199.90, "confidence_score": 0.30, "in_stock": True}
        assert _result_is_acceptable(result) is False

    def test_price_none_in_stock_true_is_not_acceptable(self):
        result = {"price": None, "confidence_score": 0.90, "in_stock": True}
        assert _result_is_acceptable(result) is False

    def test_out_of_stock_confirmed_with_high_confidence_is_acceptable(self):
        # Confirmed out-of-stock should stop the cascade
        result = {"price": None, "in_stock": False, "confidence_score": 0.75}
        assert _result_is_acceptable(result) is True

    def test_out_of_stock_confirmed_with_low_confidence_is_not_acceptable(self):
        result = {"price": None, "in_stock": False, "confidence_score": 0.30}
        assert _result_is_acceptable(result) is False

    def test_block_category_with_no_price_is_not_acceptable(self):
        result = {"price": None, "confidence_score": 0.0, "block_category": "captcha", "in_stock": None}
        assert _result_is_acceptable(result) is False


# ─── scrape_product cascade ───────────────────────────────────────────────────

class TestScrapeProductCascade:
    def test_level1_success_stops_cascade(self):
        good_result = {"price": 150.0, "confidence_score": 0.92, "in_stock": True}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: good_result}), \
             patch("execution.scraping_orchestrator.fetch_html_playwright") as mock_pw, \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://amazon.com.br/dp/test", store="amazon")
            assert result == good_result
            mock_pw.assert_not_called()
            mock_fc.assert_not_called()

    def test_level1_fail_escalates_to_level2(self):
        good_result = {"price": 150.0, "confidence_score": 0.92, "in_stock": True}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: good_result}), \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://amazon.com.br/dp/test", store="amazon")
            assert result == good_result
            mock_fc.assert_not_called()

    def test_js_store_skips_level1(self):
        good_result = {"price": 89.90, "confidence_score": 0.90, "in_stock": True}
        with patch("execution.scraping_orchestrator.fetch_html_simple") as mock_simple, \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: good_result}):
            result = scrape_product("https://mercadolivre.com/p/test", store="mercadolivre")
            assert result == good_result
            mock_simple.assert_not_called()

    def test_out_of_stock_stops_cascade_before_firecrawl(self):
        oos_result = {"price": None, "in_stock": False, "confidence_score": 0.75}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: oos_result}), \
             patch("execution.scraping_orchestrator.fetch_html_playwright") as mock_pw, \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://amazon.com.br/dp/test", store="amazon")
            assert result == oos_result
            mock_pw.assert_not_called()
            mock_fc.assert_not_called()

    def test_all_levels_fail_calls_firecrawl(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value=None), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: None}), \
             patch("execution.scraping_orchestrator.scrape_product_data", return_value={"data": {"metadata": {"price": 100.0}}}) as mock_fc:
            scrape_product("https://amazon.com.br/dp/test", store="amazon")
            mock_fc.assert_called_once()

    def test_unsupported_store_returns_none(self):
        result = scrape_product("https://shopee.com.br/test", store="shopee")
        assert result is None

    def test_login_wall_at_level2_skips_firecrawl(self):
        """login_wall at Level 2 must NOT escalate to Firecrawl (saves credits)."""
        login_block = {"price": None, "confidence_score": 0.0, "block_category": "login_wall", "in_stock": None}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: login_block}), \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://mercadolivre.com.br/p/test", store="mercadolivre")
            assert result is None
            mock_fc.assert_not_called()

    def test_access_denied_at_level2_skips_firecrawl(self):
        """access_denied at Level 2 must NOT escalate to Firecrawl."""
        blocked = {"price": None, "confidence_score": 0.0, "block_category": "access_denied", "in_stock": None}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: blocked}), \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://amazon.com.br/dp/test", store="amazon")
            assert result is None
            mock_fc.assert_not_called()

    def test_captcha_at_level2_still_escalates_to_firecrawl(self):
        """captcha/rate_limited blocks still try Firecrawl (different infra may bypass)."""
        captcha = {"price": None, "confidence_score": 0.0, "block_category": "captcha", "in_stock": None}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: captcha}), \
             patch("execution.scraping_orchestrator.scrape_product_data", return_value={}) as mock_fc:
            scrape_product("https://amazon.com.br/dp/test", store="amazon")
            mock_fc.assert_called_once()
