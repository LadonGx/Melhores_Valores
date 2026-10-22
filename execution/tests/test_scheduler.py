"""
Testes do agendador (substituto do Celery Beat) e das tarefas que ele dispara.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from execution import scheduler, worker_tasks
from execution.scheduler import CATCH_UP_DELAY, CHECK_INTERVAL, next_full_check_at

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class TestNextFullCheckAt:
    def test_first_run_ever_is_a_catch_up(self):
        assert next_full_check_at(None, NOW) == NOW + CATCH_UP_DELAY

    def test_recent_check_keeps_the_six_hour_cadence(self):
        last = NOW - timedelta(hours=2)
        assert next_full_check_at(last, NOW) == last + CHECK_INTERVAL

    def test_overdue_check_runs_soon(self):
        assert next_full_check_at(NOW - timedelta(hours=30), NOW) == NOW + CATCH_UP_DELAY

    def test_exactly_six_hours_is_overdue(self):
        assert next_full_check_at(NOW - CHECK_INTERVAL, NOW) == NOW + CATCH_UP_DELAY


class TestRunFullCheck:
    def test_enqueues_products_and_records_time(self):
        with patch.object(scheduler, "schedule_all_products", return_value={"status": "ok", "scheduled_products": 3}), \
             patch.object(scheduler, "set_last_full_check") as mock_set:
            result = scheduler.run_full_check()

        assert result["scheduled_products"] == 3
        recorded = mock_set.call_args[0][0]
        assert recorded.tzinfo is not None
        assert abs(datetime.now(timezone.utc) - recorded) < timedelta(seconds=5)


class TestStartShutdown:
    @pytest.fixture(autouse=True)
    def clean(self):
        scheduler.shutdown()
        yield
        scheduler.shutdown()

    def test_start_schedules_from_last_check_and_is_idempotent(self):
        last = datetime.now(timezone.utc) - timedelta(hours=1)
        with patch.object(scheduler, "get_last_full_check", return_value=last):
            scheduler.start()
            first = scheduler._scheduler
            scheduler.start()
            assert scheduler._scheduler is first

        job = first.get_job("full-price-check")
        assert job.next_run_time == last + CHECK_INTERVAL
        assert job.trigger.interval == CHECK_INTERVAL
        assert job.max_instances == 1 and job.coalesce is True

    def test_shutdown_is_safe_to_repeat(self):
        with patch.object(scheduler, "get_last_full_check", return_value=None):
            scheduler.start()
        scheduler.shutdown()
        scheduler.shutdown()
        assert scheduler._scheduler is None


class TestWorkerTasks:
    def _product(self, url, status="active", store="amazon"):
        p = MagicMock()
        p.url, p.store, p.status, p.name, p.imageUrl = url, store, status, f"Produto {url}", None
        return p

    def test_schedule_all_products_skips_paused_and_incomplete(self):
        products = [
            self._product("https://a"),
            self._product("https://b", status="paused"),
            self._product("https://c", store=None),
            self._product("https://d"),
        ]
        with patch.object(worker_tasks, "get_all_products", return_value=products), \
             patch.object(worker_tasks.process_price_check, "delay") as mock_delay:
            result = worker_tasks.schedule_all_products()

        assert result == {"status": "ok", "scheduled_products": 2}
        assert [c.args[0] for c in mock_delay.call_args_list] == ["https://a", "https://d"]
        # nome atual vai como fallback, para a re-checagem não gravar nome lixo
        assert mock_delay.call_args_list[0].args[2] == "Produto https://a"

    def test_search_task_uses_its_own_id_as_search_id(self):
        with patch.object(worker_tasks, "run_product_search", side_effect=lambda q, **kw: kw["search_id"]) as mock_search:
            handle = worker_tasks.task_search_products.delay("iphone", 10.0, 500.0)
            assert handle.future.result(timeout=5) == handle.id

        mock_search.assert_called_once_with("iphone", min_price=10.0, max_price=500.0, search_id=handle.id)

    def test_process_price_check_turns_exceptions_into_error_payload(self):
        with patch.object(worker_tasks, "run_price_pipeline", side_effect=RuntimeError("quebrou")):
            result = worker_tasks.process_price_check("https://a", "amazon")
        assert result == {"status": "error", "url": "https://a", "store": "amazon", "reason": "quebrou"}


class TestWebServerLifespan:
    # Chama o lifespan direto: o conftest substitui o httpx por um mock, então o
    # TestClient (que depende do httpx) não roda aqui.
    def test_lifespan_starts_and_stops_background_services(self):
        import asyncio

        from execution import web_server

        assert web_server.app.router.lifespan_context is web_server.lifespan

        async def run():
            async with web_server.lifespan(web_server.app):
                mock_start.assert_called_once()
                mock_stop.assert_not_called()

        with patch.object(web_server.scheduler, "start") as mock_start, \
             patch.object(web_server.scheduler, "shutdown") as mock_stop, \
             patch.object(web_server.task_runner, "shutdown") as mock_pool_stop:
            asyncio.run(run())
            mock_stop.assert_called_once()
            mock_pool_stop.assert_called_once()
