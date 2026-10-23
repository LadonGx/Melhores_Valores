"""
Testes da fila de tarefas em threads (substituto do Celery worker).
"""

import logging
import threading
import time

import pytest

from execution import task_runner
from execution.task_runner import task


@pytest.fixture(autouse=True)
def fresh_pool():
    task_runner.shutdown(wait=True)
    yield
    task_runner.shutdown(wait=True)


class TestTaskDecorator:
    def test_direct_call_runs_synchronously(self):
        @task
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_keeps_function_metadata(self):
        @task
        def documented():
            """docstring"""

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "docstring"

    def test_delay_runs_in_background_and_returns_id(self):
        caller = threading.current_thread().name

        @task
        def where(x):
            return threading.current_thread().name, x

        handle = where.delay(42)
        thread_name, value = handle.future.result(timeout=5)
        assert value == 42
        assert thread_name != caller and thread_name.startswith("mv-user")
        assert len(handle.id) == 36  # uuid4

    def test_delay_accepts_kwargs(self):
        @task
        def greet(name, greeting="olá"):
            return f"{greeting} {name}"

        assert greet.delay("Ana", greeting="oi").future.result(timeout=5) == "oi Ana"

    def test_bind_injects_request_id_equal_to_handle_id(self):
        @task(bind=True)
        def my_id(self):
            return self.request.id

        handle = my_id.delay()
        assert handle.future.result(timeout=5) == handle.id

    def test_bind_direct_call_gets_a_fresh_id(self):
        @task(bind=True)
        def my_id(self):
            return self.request.id

        assert my_id() != my_id()

    def test_exception_is_logged_and_kept_in_future(self, caplog):
        @task
        def boom():
            raise RuntimeError("falhou")

        with caplog.at_level(logging.ERROR, logger="execution.task_runner"):
            handle = boom.delay()
            with pytest.raises(RuntimeError):
                handle.future.result(timeout=5)
        assert "Tarefa boom falhou" in caplog.text
        assert handle.id in caplog.text


class TestPool:
    def test_at_most_max_workers_run_at_once(self):
        running = 0
        peak = 0
        lock = threading.Lock()

        @task
        def slow():
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.05)
            with lock:
                running -= 1

        handles = [slow.delay() for _ in range(6)]
        for h in handles:
            h.future.result(timeout=5)
        assert peak == task_runner.MAX_WORKERS

    def test_shutdown_discards_queued_tasks_and_pool_restarts(self):
        release = threading.Event()

        @task
        def blocker():
            release.wait(5)

        running = [blocker.delay() for _ in range(task_runner.MAX_WORKERS)]
        queued = blocker.delay()
        task_runner.shutdown(wait=False)
        release.set()

        assert queued.future.cancelled()
        for h in running:
            h.future.result(timeout=5)

        @task
        def after():
            return "ok"

        assert after.delay().future.result(timeout=5) == "ok"


class TestQueues:
    def test_apply_async_runs_on_background_queue(self):
        @task
        def where():
            return threading.current_thread().name

        handle = where.apply_async(queue="background")
        assert handle.future.result(timeout=5).startswith("mv-background")

    def test_apply_async_passes_args_and_kwargs(self):
        @task
        def greet(name, greeting="olá"):
            return f"{greeting} {name}"

        handle = greet.apply_async(("Ana",), {"greeting": "oi"}, queue="background")
        assert handle.future.result(timeout=5) == "oi Ana"

    def test_unknown_queue_is_rejected(self):
        @task
        def noop():
            pass

        with pytest.raises(ValueError, match="Fila desconhecida"):
            noop.apply_async(queue="prioridade")

    def test_user_task_does_not_wait_for_a_busy_background_queue(self):
        """O motivo das duas filas: busca/adicionar produto não esperam o lote de checagens."""
        release = threading.Event()

        @task
        def slow_batch_item():
            release.wait(5)

        @task
        def user_action():
            return "pronto"

        busy = [slow_batch_item.apply_async(queue="background") for _ in range(6)]
        try:
            assert user_action.delay().future.result(timeout=2) == "pronto"
        finally:
            release.set()
            for h in busy:
                h.future.result(timeout=10)

    def test_shutdown_stops_every_queue(self):
        release = threading.Event()

        @task
        def blocker():
            release.wait(5)

        running = [blocker.apply_async(queue="background") for _ in range(task_runner.QUEUES["background"])]
        queued = blocker.apply_async(queue="background")
        task_runner.shutdown(wait=False)
        release.set()
        assert queued.future.cancelled()
        for h in running:
            h.future.result(timeout=5)