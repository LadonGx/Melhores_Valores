"""
Unit tests for worker_tasks.run_price_pipeline.

All DB and scraping calls are mocked so these run without Docker.
"""

from unittest.mock import patch, MagicMock
import pytest

from execution.scraping_orchestrator import ScrapeOutcome
from execution.worker_tasks import run_price_pipeline


def _outcome(result, block=None, level=2, duration_ms=1234):
    """Retorno de scrape_product_with_meta (cascata mockada)."""
    return ScrapeOutcome(result, block, level, duration_ms)


def _make_product(product_id="prod-1", name="Produto Teste"):
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.imageUrl = None
    return p


# ─── Helpers ──────────────────────────────────────────────────────────────────

MOCK_PATCHES = {
    "scrape": "execution.worker_tasks.scrape_product_with_meta",
    "cache_get": "execution.worker_tasks.get_cached_price",
    "cache_set": "execution.worker_tasks.set_cached_price",
    "get_or_create": "execution.worker_tasks.get_or_create_product",
    "add_history": "execution.worker_tasks.add_price_history",
    "last_price": "execution.worker_tasks.get_last_valid_price_for_url",
    # Imported as `is_garbage_name as _is_garbage_name` in worker_tasks
    "is_garbage": "execution.worker_tasks._is_garbage_name",
    "normalize_store": "execution.worker_tasks.normalize_store",
    "mark": "execution.worker_tasks.mark_product_checked",
    "record": "execution.worker_tasks.record_check_attempt",
    "set_format": "execution.worker_tasks.set_product_format",
}


@pytest.fixture(autouse=True)
def mark_checked():
    """mark_product_checked mockado em todos os testes; devolve o mock para asserts."""
    with patch(MOCK_PATCHES["mark"]) as mock_mark:
        yield mock_mark


@pytest.fixture(autouse=True)
def record_attempt():
    """record_check_attempt mockado em todos os testes; devolve o mock para asserts."""
    with patch(MOCK_PATCHES["record"]) as mock_record:
        yield mock_record


@pytest.fixture(autouse=True)
def set_format():
    """set_product_format mockado em todos os testes; devolve o mock para asserts."""
    with patch(MOCK_PATCHES["set_format"]) as mock_set_format:
        yield mock_set_format


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
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
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
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "ok"
            assert result["price"] == 199.90
            assert result["in_stock"] is True
            mock_history.assert_called_once_with(
                product_id="prod-1", price=199.90, in_stock=True, seller_type=None, seller_name=None
            )

    def test_scrape_success_saves_seller(self):
        """Vendedor identificado pelo adapter vai para o histórico (terceiro não é descartado)."""
        product = _make_product()
        scrape_result = {
            "price": 180.64, "name": "Produto", "image_url": None, "in_stock": True,
            "confidence_score": 0.92, "offer_type": "main",
            "seller_type": "third_party", "seller_name": "JS Digital BR",
        }
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            mock_history.assert_called_once_with(
                product_id="prod-1", price=180.64, in_stock=True,
                seller_type="third_party", seller_name="JS Digital BR",
            )

    def test_scrape_success_updates_cache(self):
        product = _make_product()
        scrape_result = {"price": 99.0, "name": "Produto", "image_url": None, "in_stock": True, "confidence_score": 0.9}
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]), \
             patch(MOCK_PATCHES["cache_set"]) as mock_cache_set, \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            mock_cache_set.assert_called_once()


# ─── Failure and out-of-stock paths ───────────────────────────────────────────

class TestFailureAndOutOfStock:
    def test_cascade_failure_does_not_touch_history(self):
        """A technical extraction failure (timeout, block, etc.) must not be
        recorded as 'out of stock' — no adapter ever confirmed unavailability,
        so the price history should be left untouched."""
        product = _make_product()
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(None)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon", fallback_name="Produto Teste")
            assert result["status"] == "error"
            mock_history.assert_not_called()

    def test_out_of_stock_confirmed_records_history(self):
        product = _make_product()
        scrape_result = {"price": None, "in_stock": False, "confidence_score": 0.75, "name": "Produto", "image_url": None}
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
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
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
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

    def test_firecrawl_confirmed_out_of_stock_records_history(self):
        """Regressão: quando níveis 1/2 falham e o Firecrawl (nível 3) é quem alcança a
        página real e confirma indisponibilidade (`available: False`), o pipeline deve
        gravar `in_stock: False` — antes desse fix, o caminho do Firecrawl nunca setava
        `in_stock`, caindo no ramo genérico de 'preço inválido' e não gravando nada."""
        product = _make_product()
        # Formato bruto retornado por scrape_product_data (Firecrawl) — contém "data",
        # o que faz run_price_pipeline rotear para parse_product_data (não mockado aqui).
        scrape_result = {
            "data": {
                "metadata": {"title": "Livro O Caminho Dos Reis", "price": 0, "available": False}
            }
        }
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["last_price"], return_value=None), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://mercadolivre.com.br/produto", "mercadolivre")
            assert result["status"] == "out_of_stock"
            mock_history.assert_called_once_with(product_id="prod-1", price=None, in_stock=False)


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
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
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
             patch(MOCK_PATCHES["scrape"], return_value=_outcome(scrape_result)), \
             patch(MOCK_PATCHES["get_or_create"], return_value=product), \
             patch(MOCK_PATCHES["add_history"]) as mock_history, \
             patch(MOCK_PATCHES["cache_set"]), \
             patch(MOCK_PATCHES["last_price"], return_value=199.90), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            result = run_price_pipeline("https://amazon.com.br/dp/test", "amazon")
            assert result["status"] == "ok"
            mock_history.assert_called_once()


# ─── Registro da última verificação (mark_product_checked) ────────────────────

URL = "https://amazon.com.br/dp/test"


def _pipeline_patches(scrape_return, product=None, last_price=None):
    """Patches comuns do caminho 'cache miss + scraping'; devolve o ExitStack já aberto."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch(MOCK_PATCHES["cache_get"], return_value=None))
    stack.enter_context(patch(MOCK_PATCHES["scrape"], return_value=scrape_return))
    stack.enter_context(patch(MOCK_PATCHES["get_or_create"], return_value=product or _make_product()))
    stack.enter_context(patch(MOCK_PATCHES["cache_set"]))
    stack.enter_context(patch(MOCK_PATCHES["last_price"], return_value=last_price))
    stack.enter_context(patch(MOCK_PATCHES["is_garbage"], return_value=False))
    return stack


class TestLastCheckMarking:
    def test_successful_scrape_marks_ok(self, mark_checked):
        result = {"price": 199.90, "name": "Produto", "in_stock": True, "confidence_score": 0.92}
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]):
            run_price_pipeline(URL, "amazon")
        mark_checked.assert_called_once_with("prod-1", "ok")

    def test_deduplicated_history_still_marks_ok(self, mark_checked):
        """add_price_history devolve None quando nada mudou no dia — a checagem
        aconteceu mesmo assim, e é isso que 'Última verificação' mostra."""
        result = {"price": 199.90, "name": "Produto", "in_stock": True, "confidence_score": 0.92}
        with _pipeline_patches(_outcome(result)), \
             patch(MOCK_PATCHES["add_history"], return_value=None) as mock_history:
            payload = run_price_pipeline(URL, "amazon")
        assert payload["status"] == "ok"
        mock_history.assert_called_once()
        mark_checked.assert_called_once_with("prod-1", "ok")

    def test_third_party_from_offer_follows_normal_path(self, mark_checked):
        result = {
            "price": 120.0, "name": "Produto", "in_stock": True,
            "confidence_score": 0.6, "offer_type": "third_party_from",
            "seller_type": "third_party_from", "seller_name": None,
        }
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]) as mock_history:
            payload = run_price_pipeline(URL, "amazon")
        assert payload["status"] == "ok"
        mock_history.assert_called_once_with(
            product_id="prod-1", price=120.0, in_stock=True,
            seller_type="third_party_from", seller_name=None,
        )
        mark_checked.assert_called_once_with("prod-1", "ok")

    def test_out_of_stock_marks_out_of_stock(self, mark_checked):
        result = {"price": None, "in_stock": False, "confidence_score": 0.75, "name": "Produto"}
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]):
            payload = run_price_pipeline(URL, "amazon")
        assert payload["status"] == "out_of_stock"
        mark_checked.assert_called_once_with("prod-1", "out_of_stock")

    def test_no_offer_marks_no_offer_and_skips_history(self, mark_checked):
        result = {
            "price": None, "in_stock": True, "confidence_score": 0.6,
            "offer_type": "none", "block_category": None, "name": "Produto",
        }
        with _pipeline_patches(_outcome(result)), \
             patch(MOCK_PATCHES["add_history"]) as mock_history:
            payload = run_price_pipeline(URL, "amazon")
        assert payload == {
            "status": "no_offer",
            "url": URL,
            "store": "amazon",
            "reason": "Anúncio sem oferta principal.",
        }
        mock_history.assert_not_called()
        mark_checked.assert_called_once_with("prod-1", "no_offer")

    def test_cascade_failure_with_block_marks_blocked(self, mark_checked):
        with _pipeline_patches(_outcome(None, "captcha")), patch(MOCK_PATCHES["add_history"]) as mock_history:
            payload = run_price_pipeline(URL, "amazon", fallback_name="Produto Teste")
        assert payload["status"] == "error"
        mock_history.assert_not_called()
        mark_checked.assert_called_once_with("prod-1", "blocked", "captcha")

    def test_cascade_failure_without_block_marks_scrape_failed(self, mark_checked):
        with _pipeline_patches(_outcome(None, None, level=3)), patch(MOCK_PATCHES["add_history"]):
            run_price_pipeline(URL, "amazon", fallback_name="Produto Teste")
        mark_checked.assert_called_once_with("prod-1", "error", "scrape_failed")

    def test_invalid_price_marks_invalid_price(self, mark_checked):
        result = {"price": None, "in_stock": True, "confidence_score": 0.8, "name": "Produto"}
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]) as mock_history:
            payload = run_price_pipeline(URL, "amazon")
        assert payload["status"] == "error"
        mock_history.assert_not_called()
        mark_checked.assert_called_once_with("prod-1", "error", "invalid_price")

    def test_sanity_check_rejection_marks_price_rejected(self, mark_checked):
        result = {"price": 9999.0, "name": "Produto", "in_stock": True, "confidence_score": 0.6}
        with _pipeline_patches(_outcome(result), last_price=199.90), \
             patch(MOCK_PATCHES["add_history"]) as mock_history:
            payload = run_price_pipeline(URL, "amazon")
        assert payload["status"] == "error"
        mock_history.assert_not_called()
        mark_checked.assert_called_once_with("prod-1", "error", "price_rejected")

    def test_cache_hit_does_not_mark(self, mark_checked):
        with patch(MOCK_PATCHES["cache_get"], return_value={"price": 199.90, "name": "Produto"}), \
             patch(MOCK_PATCHES["get_or_create"], return_value=_make_product()), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            payload = run_price_pipeline(URL, "amazon")
        assert payload["source"] == "cache"
        mark_checked.assert_not_called()

    def test_unexpected_exception_marks_exception_and_reraises(self, mark_checked):
        product = _make_product()
        with _pipeline_patches(_outcome(dict(price=10.0, in_stock=True, confidence_score=0.9, name="P")), product), \
             patch(MOCK_PATCHES["add_history"], side_effect=RuntimeError("banco caiu")):
            with pytest.raises(RuntimeError):
                run_price_pipeline(URL, "amazon")
        mark_checked.assert_called_once_with("prod-1", "error", "exception")

    def test_scrape_exception_marks_exception_and_reraises(self, mark_checked):
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], side_effect=RuntimeError("playwright caiu")), \
             patch(MOCK_PATCHES["get_or_create"], return_value=_make_product()), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            with pytest.raises(RuntimeError, match="playwright caiu"):
                run_price_pipeline(URL, "amazon")
        mark_checked.assert_called_once_with("prod-1", "error", "exception")

    def test_failure_to_mark_exception_does_not_mask_original_error(self, mark_checked):
        with patch(MOCK_PATCHES["cache_get"], return_value=None), \
             patch(MOCK_PATCHES["scrape"], side_effect=RuntimeError("playwright caiu")), \
             patch(MOCK_PATCHES["get_or_create"], side_effect=RuntimeError("banco fora")), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            with pytest.raises(RuntimeError, match="playwright caiu"):
                run_price_pipeline(URL, "amazon")
        mark_checked.assert_not_called()


# ─── Medição: record_check_attempt + trigger ──────────────────────────────────

class TestCheckAttemptRecording:
    def _run(self, scrape_return, trigger=None, last_price=None):
        kwargs = {} if trigger is None else {"trigger": trigger}
        with _pipeline_patches(scrape_return, last_price=last_price), \
             patch(MOCK_PATCHES["add_history"]):
            return run_price_pipeline(URL, "amazon", **kwargs)

    def test_ok(self, record_attempt):
        result = {"price": 199.90, "name": "P", "in_stock": True, "confidence_score": 0.92}
        self._run(_outcome(result, level=1, duration_ms=800))
        record_attempt.assert_called_once()
        args, kwargs = record_attempt.call_args
        assert args == ("prod-1", "amazon", "ok")
        assert kwargs["block_category"] is None and kwargs["error"] is None
        assert kwargs["level"] == 1
        assert kwargs["trigger"] == "added"  # padrão
        assert kwargs["duration_ms"] >= 800

    def test_out_of_stock(self, record_attempt):
        result = {"price": None, "in_stock": False, "confidence_score": 0.75, "name": "P"}
        self._run(_outcome(result, level=2))
        assert record_attempt.call_args.args == ("prod-1", "amazon", "out_of_stock")
        assert record_attempt.call_args.kwargs["level"] == 2

    def test_no_offer(self, record_attempt):
        result = {"price": None, "in_stock": True, "confidence_score": 0.6, "offer_type": "none", "name": "P"}
        self._run(_outcome(result))
        assert record_attempt.call_args.args == ("prod-1", "amazon", "no_offer")

    def test_blocked_with_category(self, record_attempt):
        self._run(_outcome(None, "login_wall", level=2, duration_ms=29000))
        record_attempt.assert_called_once_with(
            "prod-1", "amazon", "blocked",
            block_category="login_wall", error=None, level=2, duration_ms=29000, trigger="added",
        )

    def test_scrape_failed(self, record_attempt):
        self._run(_outcome(None, None, level=3, duration_ms=5000))
        record_attempt.assert_called_once_with(
            "prod-1", "amazon", "error",
            block_category=None, error="scrape_failed", level=3, duration_ms=5000, trigger="added",
        )

    def test_invalid_price(self, record_attempt):
        result = {"price": None, "in_stock": True, "confidence_score": 0.8, "name": "P"}
        self._run(_outcome(result))
        args, kwargs = record_attempt.call_args
        assert args == ("prod-1", "amazon", "error")
        assert kwargs["error"] == "invalid_price" and kwargs["block_category"] is None

    def test_price_rejected(self, record_attempt):
        result = {"price": 9999.0, "name": "P", "in_stock": True, "confidence_score": 0.6}
        self._run(_outcome(result), last_price=199.90)
        args, kwargs = record_attempt.call_args
        assert args == ("prod-1", "amazon", "error")
        assert kwargs["error"] == "price_rejected"

    def test_unexpected_exception(self, record_attempt):
        with _pipeline_patches(_outcome(dict(price=10.0, in_stock=True, confidence_score=0.9, name="P"))), \
             patch(MOCK_PATCHES["add_history"], side_effect=RuntimeError("banco caiu")):
            with pytest.raises(RuntimeError):
                run_price_pipeline(URL, "amazon", trigger="manual")
        record_attempt.assert_called_once_with(
            "prod-1", "amazon", "error",
            block_category=None, error="exception", level=None, duration_ms=None, trigger="manual",
        )

    @pytest.mark.parametrize("trigger", ["scheduled", "manual", "added"])
    def test_trigger_is_recorded(self, record_attempt, trigger):
        result = {"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9}
        self._run(_outcome(result), trigger=trigger)
        assert record_attempt.call_args.kwargs["trigger"] == trigger

    def test_every_marked_check_is_also_recorded(self, mark_checked, record_attempt):
        for scrape in (_outcome({"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9}),
                       _outcome(None, "captcha"), _outcome(None, None)):
            mark_checked.reset_mock()
            record_attempt.reset_mock()
            self._run(scrape)
            assert mark_checked.call_count == record_attempt.call_count == 1
            assert mark_checked.call_args.args[1] == record_attempt.call_args.args[2]

    def test_cache_hit_records_nothing(self, record_attempt):
        with patch(MOCK_PATCHES["cache_get"], return_value={"price": 199.90, "name": "Produto"}), \
             patch(MOCK_PATCHES["get_or_create"], return_value=_make_product()), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline(URL, "amazon")
        record_attempt.assert_not_called()


# ─── Trava do ML no pipeline e na task ────────────────────────────────────────

from execution.store_lock import StoreBusyError  # noqa: E402
from execution import worker_tasks  # noqa: E402


class TestStoreBusy:
    def _busy(self):
        return patch(MOCK_PATCHES["scrape"], side_effect=StoreBusyError("ocupada"))

    def test_busy_does_not_mark_record_or_write_anything(self, mark_checked, record_attempt, set_format):
        with patch(MOCK_PATCHES["cache_get"], return_value=None), self._busy(), \
             patch(MOCK_PATCHES["get_or_create"]) as mock_get, \
             patch(MOCK_PATCHES["add_history"]) as mock_history:
            with pytest.raises(StoreBusyError):
                run_price_pipeline("https://mercadolivre.com.br/p/x", "mercadolivre")
        mark_checked.assert_not_called()
        record_attempt.assert_not_called()
        set_format.assert_not_called()
        mock_get.assert_not_called()
        mock_history.assert_not_called()

    @pytest.mark.parametrize(
        "trigger, expected", [("manual", 60.0), ("scheduled", 240.0), ("added", 240.0)]
    )
    def test_lock_wait_depends_on_trigger(self, trigger, expected):
        result = {"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9}
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]),              patch(MOCK_PATCHES["scrape"], return_value=_outcome(result)) as mock_scrape:
            run_price_pipeline(URL, "amazon", trigger=trigger)
        assert mock_scrape.call_args.kwargs["lock_wait_s"] == expected


class FakeTask:
    """Faz o papel do `self` de uma task Celery com bind=True."""

    class Retry(Exception):
        pass

    def __init__(self, retries=0):
        self.request = MagicMock(retries=retries)
        self.retry_calls = []

    def retry(self, exc=None, countdown=None, max_retries=None):
        self.retry_calls.append({"exc": exc, "countdown": countdown, "max_retries": max_retries})
        return FakeTask.Retry("retry")


class TestTaskBusyRetry:
    def test_busy_reschedules_with_random_countdown_between_60_and_180(self):
        task = FakeTask(retries=0)
        with patch("execution.worker_tasks.run_price_pipeline", side_effect=StoreBusyError("x")):
            with pytest.raises(FakeTask.Retry):
                worker_tasks.run_price_check_task(task, URL, "mercadolivre", trigger="scheduled")
        call = task.retry_calls[0]
        assert 60 <= call["countdown"] <= 180
        assert call["max_retries"] == 3
        assert isinstance(call["exc"], StoreBusyError)

    def test_pipeline_receives_the_trigger(self):
        with patch("execution.worker_tasks.run_price_pipeline", return_value={"status": "ok"}) as pipeline:
            worker_tasks.run_price_check_task(FakeTask(), URL, "amazon", "Nome", "img", "scheduled")
        pipeline.assert_called_once_with(
            url=URL, store="amazon", fallback_name="Nome", fallback_image="img", trigger="scheduled"
        )

    def test_retries_exhausted_returns_busy_without_raising(self):
        task = FakeTask(retries=3)
        with patch("execution.worker_tasks.run_price_pipeline", side_effect=StoreBusyError("x")):
            result = worker_tasks.run_price_check_task(task, URL, "mercadolivre", trigger="scheduled")
        assert result == {"status": "error", "url": URL, "store": "mercadolivre", "reason": "busy"}
        assert task.retry_calls == []

    def test_other_exceptions_still_return_error_payload(self):
        task = FakeTask()
        with patch("execution.worker_tasks.run_price_pipeline", side_effect=RuntimeError("boom")):
            result = worker_tasks.run_price_check_task(task, URL, "amazon")
        assert result["status"] == "error" and result["reason"] == "boom"
        assert task.retry_calls == []


# ─── Formato (Kindle/físico) ──────────────────────────────────────────────────

class TestProductFormat:
    def _run(self, result, **kwargs):
        with _pipeline_patches(_outcome(result)), patch(MOCK_PATCHES["add_history"]):
            return run_price_pipeline(URL, "amazon", **kwargs)

    def test_ok_with_format_key_sets_format(self, set_format):
        self._run({"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9, "format": "ebook_kindle"})
        set_format.assert_called_once_with("prod-1", "ebook_kindle")

    def test_format_none_is_forwarded(self, set_format):
        self._run({"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9, "format": None})
        set_format.assert_called_once_with("prod-1", None)

    def test_ok_without_format_key_does_not_touch_it(self, set_format):
        self._run({"price": 10.0, "name": "P", "in_stock": True, "confidence_score": 0.9})
        set_format.assert_not_called()

    def test_out_of_stock_and_no_offer_set_format(self, set_format):
        self._run({"price": None, "in_stock": False, "confidence_score": 0.75, "name": "P", "format": "physical"})
        self._run({"price": None, "in_stock": True, "confidence_score": 0.6, "offer_type": "none",
                   "name": "P", "format": "physical"})
        assert set_format.call_count == 2

    def test_failures_never_set_format(self, set_format):
        # preço inválido (erro) e rejeitado pelo sanity check: mesmo com a chave, não grava
        self._run({"price": None, "in_stock": True, "confidence_score": 0.8, "name": "P", "format": "physical"})
        with _pipeline_patches(
            _outcome({"price": 9999.0, "name": "P", "in_stock": True, "confidence_score": 0.6, "format": "physical"}),
            last_price=199.90,
        ), patch(MOCK_PATCHES["add_history"]):
            run_price_pipeline(URL, "amazon")
        with _pipeline_patches(_outcome(None, "captcha")), patch(MOCK_PATCHES["add_history"]):
            run_price_pipeline(URL, "amazon")
        set_format.assert_not_called()

    def test_cache_hit_does_not_set_format(self, set_format):
        with patch(MOCK_PATCHES["cache_get"], return_value={"price": 199.90, "name": "Produto"}), \
             patch(MOCK_PATCHES["get_or_create"], return_value=_make_product()), \
             patch(MOCK_PATCHES["is_garbage"], return_value=False):
            run_price_pipeline(URL, "amazon")
        set_format.assert_not_called()
