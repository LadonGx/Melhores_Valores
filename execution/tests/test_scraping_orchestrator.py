"""
Unit tests for scraping_orchestrator.py

Tests cascade logic: level skipping, result acceptance threshold,
out-of-stock early stop, and Firecrawl escalation.
"""

from unittest.mock import patch, MagicMock
import pytest

from execution.scraping_orchestrator import _result_is_acceptable, scrape_product, scrape_product_with_block


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


# ─── offer_type == "none" (anúncio sem oferta principal) ──────────────────────

class TestNoOfferResult:
    def test_no_offer_with_enough_confidence_is_acceptable(self):
        result = {"price": None, "in_stock": True, "confidence_score": 0.6, "offer_type": "none"}
        assert _result_is_acceptable(result) is True

    def test_no_offer_with_low_confidence_is_not_acceptable(self):
        result = {"price": None, "in_stock": True, "confidence_score": 0.3, "offer_type": "none"}
        assert _result_is_acceptable(result) is False

    def test_no_offer_stops_cascade_before_firecrawl(self):
        no_offer = {"price": None, "in_stock": True, "confidence_score": 0.6, "offer_type": "none"}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: no_offer}), \
             patch("execution.scraping_orchestrator.fetch_html_playwright") as mock_pw, \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result = scrape_product("https://amazon.com.br/dp/test", store="amazon")
            assert result == no_offer
            mock_pw.assert_not_called()
            mock_fc.assert_not_called()


# ─── scrape_product_with_block ────────────────────────────────────────────────

class TestScrapeProductWithBlock:
    def test_success_returns_result_without_block(self):
        good_result = {"price": 150.0, "confidence_score": 0.92, "in_stock": True}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html>ok</html>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: good_result}):
            result, block = scrape_product_with_block("https://amazon.com.br/dp/test", store="amazon")
        assert result == good_result
        assert block is None

    def test_login_wall_returns_block_category(self):
        login_block = {"price": None, "confidence_score": 0.0, "block_category": "login_wall", "in_stock": None}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: login_block}), \
             patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
            result, block = scrape_product_with_block("https://mercadolivre.com.br/p/test", store="mercadolivre")
        assert result is None
        assert block == "login_wall"
        mock_fc.assert_not_called()

    def test_failure_without_block_returns_no_category(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value=None), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: None}), \
             patch("execution.scraping_orchestrator.scrape_product_data", return_value=None):
            result, block = scrape_product_with_block("https://amazon.com.br/dp/test", store="amazon")
        assert result is None
        assert block is None


# ─── Nível da cascata, trava do ML e perfil do navegador ──────────────────────

from execution.scraping_orchestrator import ScrapeOutcome, scrape_product_with_meta
from execution.store_lock import StoreBusyError

GOOD = {"price": 150.0, "confidence_score": 0.92, "in_stock": True}
ML_URL = "https://mercadolivre.com.br/p/test"
AMAZON_URL = "https://amazon.com.br/dp/test"


class TestCascadeLevel:
    def test_level1_success_reports_level_1(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: GOOD}):
            outcome = scrape_product_with_meta(AMAZON_URL, store="amazon")
        assert isinstance(outcome, ScrapeOutcome)
        assert (outcome.result, outcome.block_category, outcome.level) == (GOOD, None, 1)
        assert outcome.duration_ms is not None and outcome.duration_ms >= 0

    def test_playwright_success_reports_level_2(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: GOOD}):
            assert scrape_product_with_meta(AMAZON_URL, store="amazon").level == 2

    def test_firecrawl_result_reports_level_3(self):
        fc = {"data": {"metadata": {"price": 10.0}}}
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value=None), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: None}), \
             patch("execution.scraping_orchestrator.scrape_product_data", return_value=fc):
            outcome = scrape_product_with_meta(AMAZON_URL, store="amazon")
        assert (outcome.result, outcome.level) == (fc, 3)

    def test_failure_reports_last_level_tried(self):
        login = {"price": None, "confidence_score": 0.0, "block_category": "login_wall", "in_stock": None}
        with patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: login}):
            outcome = scrape_product_with_meta(ML_URL, store="mercadolivre")
        assert (outcome.result, outcome.block_category, outcome.level) == (None, "login_wall", 2)

    def test_firecrawl_failure_reports_level_3(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value=None), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: None}), \
             patch("execution.scraping_orchestrator.scrape_product_data", return_value=None):
            outcome = scrape_product_with_meta(AMAZON_URL, store="amazon")
        assert (outcome.result, outcome.level) == (None, 3)

    def test_unsupported_store_has_no_level(self):
        outcome = scrape_product_with_meta("https://shopee.com.br/x", store="shopee")
        assert (outcome.result, outcome.block_category, outcome.level) == (None, None, None)

    def test_block_wrapper_is_unchanged(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: GOOD}):
            assert scrape_product_with_block(AMAZON_URL, store="amazon") == (GOOD, None)


class TestMercadoLivreLock:
    def test_whole_ml_cascade_runs_inside_the_lock(self, fake_store_lock_redis):
        seen = {}

        def adapter(html):
            seen["held"] = list(fake_store_lock_redis.acquired)
            seen["released"] = list(fake_store_lock_redis.released)
            return GOOD

        with patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": adapter}):
            scrape_product_with_block(ML_URL, store="mercadolivre")
        assert seen["held"] == ["store_lock:mercadolivre"]
        assert seen["released"] == []  # ainda segurando durante o parsing
        assert fake_store_lock_redis.released == ["store_lock:mercadolivre"]

    def test_lock_released_when_the_cascade_raises(self, fake_store_lock_redis):
        with patch("execution.scraping_orchestrator.fetch_html_playwright", side_effect=RuntimeError("boom")), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: GOOD}):
            with pytest.raises(RuntimeError):
                scrape_product_with_block(ML_URL, store="mercadolivre")
        assert fake_store_lock_redis.released == ["store_lock:mercadolivre"]

    def test_amazon_does_not_use_the_lock(self, fake_store_lock_redis):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: GOOD}):
            scrape_product_with_block(AMAZON_URL, store="amazon")
        assert fake_store_lock_redis.created == []

    def test_wait_is_passed_to_the_lock(self, fake_store_lock_redis):
        with patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: GOOD}):
            scrape_product_with_block(ML_URL, store="mercadolivre", lock_wait_s=17)
        assert fake_store_lock_redis.created[0]["blocking_timeout"] == 17.0

    def test_busy_lock_raises_without_scraping_or_recording_health(
        self, fake_store_lock_redis, fake_store_health_redis
    ):
        holding = fake_store_lock_redis.lock("store_lock:mercadolivre", timeout=300, blocking_timeout=1)
        assert holding.acquire()
        try:
            with patch("execution.scraping_orchestrator.fetch_html_playwright") as mock_pw, \
                 patch("execution.scraping_orchestrator.scrape_product_data") as mock_fc:
                with pytest.raises(StoreBusyError):
                    scrape_product_with_meta(ML_URL, store="mercadolivre", lock_wait_s=0.05)
            mock_pw.assert_not_called()
            mock_fc.assert_not_called()
        finally:
            holding.release()
        assert fake_store_health_redis.data == {}  # nenhuma checagem aconteceu: saúde intacta

    def test_health_is_recorded_for_real_checks(self, fake_store_health_redis):
        with patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>"), \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: GOOD}):
            scrape_product_with_block(ML_URL, store="mercadolivre")
        assert "last_ok_at" in fake_store_health_redis.data["store_health:mercadolivre:monitor"]


class TestBrowserProfile:
    def test_ml_level2_uses_the_mercadolivre_profile(self):
        with patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>") as mock_pw, \
             patch("execution.scraping_orchestrator.ADAPTERS", {"mercadolivre": lambda html: GOOD}):
            scrape_product_with_block(ML_URL, store="mercadolivre")
        mock_pw.assert_called_once_with(ML_URL, profile="mercadolivre")

    def test_amazon_level2_keeps_the_disposable_context(self):
        with patch("execution.scraping_orchestrator.fetch_html_simple", return_value=None), \
             patch("execution.scraping_orchestrator.fetch_html_playwright", return_value="<html/>") as mock_pw, \
             patch("execution.scraping_orchestrator.ADAPTERS", {"amazon": lambda html: GOOD}):
            scrape_product_with_block(AMAZON_URL, store="amazon")
        mock_pw.assert_called_once_with(AMAZON_URL)
