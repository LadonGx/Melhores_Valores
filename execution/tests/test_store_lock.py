"""
Testes da trava global por loja (execution/store_lock.py).

Usa o Redis falso do conftest (`fake_store_lock_redis`): sem rede, sem Redis real.
"""

import threading

import pytest

from execution.store_lock import (
    DEFAULT_LOCK_WAIT_S,
    StoreBusyError,
    store_check_lock,
)


class TestLockedStore:
    def test_ml_takes_and_releases_the_global_lock(self, fake_store_lock_redis):
        with store_check_lock("mercadolivre", 5):
            assert fake_store_lock_redis.acquired == ["store_lock:mercadolivre"]
            assert fake_store_lock_redis.released == []
        assert fake_store_lock_redis.released == ["store_lock:mercadolivre"]

    def test_lock_uses_expiry_and_wait(self, fake_store_lock_redis):
        with store_check_lock("mercadolivre", 42):
            pass
        assert fake_store_lock_redis.created == [
            {"name": "store_lock:mercadolivre", "timeout": 300.0, "blocking_timeout": 42.0}
        ]

    def test_expiry_follows_env(self, fake_store_lock_redis, monkeypatch):
        monkeypatch.setenv("ML_LOCK_TIMEOUT_S", "90")
        with store_check_lock("mercadolivre", 1):
            pass
        assert fake_store_lock_redis.created[0]["timeout"] == 90.0

    def test_default_wait_when_not_given(self, fake_store_lock_redis):
        with store_check_lock("mercadolivre"):
            pass
        assert fake_store_lock_redis.created[0]["blocking_timeout"] == DEFAULT_LOCK_WAIT_S

    def test_released_even_when_the_body_raises(self, fake_store_lock_redis):
        with pytest.raises(RuntimeError, match="playwright caiu"):
            with store_check_lock("mercadolivre", 5):
                raise RuntimeError("playwright caiu")
        assert fake_store_lock_redis.released == ["store_lock:mercadolivre"]
        # e a trava volta a ficar livre para a próxima checagem
        with store_check_lock("mercadolivre", 0):
            pass

    def test_second_check_waits_and_gets_busy_error_when_wait_runs_out(self, fake_store_lock_redis):
        inside, leave = threading.Event(), threading.Event()

        def holder():
            with store_check_lock("mercadolivre", 5):
                inside.set()
                leave.wait(5)

        t = threading.Thread(target=holder)
        t.start()
        try:
            assert inside.wait(5)
            with pytest.raises(StoreBusyError):
                with store_check_lock("mercadolivre", 0.05):
                    pytest.fail("não podia entrar com a trava ocupada")
        finally:
            leave.set()
            t.join(5)
        # depois que a primeira sai, a segunda consegue
        with store_check_lock("mercadolivre", 0.05):
            pass

    def test_two_checks_never_run_inside_together(self, fake_store_lock_redis):
        """Várias threads disputando a trava: nunca mais de uma dentro ao mesmo tempo."""
        state = {"inside": 0, "max_inside": 0}
        guard = threading.Lock()

        def check():
            with store_check_lock("mercadolivre", 10):
                with guard:
                    state["inside"] += 1
                    state["max_inside"] = max(state["max_inside"], state["inside"])
                threading.Event().wait(0.02)
                with guard:
                    state["inside"] -= 1

        threads = [threading.Thread(target=check) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        assert state["max_inside"] == 1
        assert len(fake_store_lock_redis.released) == 6

    def test_busy_error_does_not_release_a_lock_it_never_got(self, fake_store_lock_redis):
        inside, leave = threading.Event(), threading.Event()

        def holder():
            with store_check_lock("mercadolivre", 5):
                inside.set()
                leave.wait(5)

        t = threading.Thread(target=holder)
        t.start()
        try:
            assert inside.wait(5)
            with pytest.raises(StoreBusyError):
                with store_check_lock("mercadolivre", 0):
                    pass
            assert fake_store_lock_redis.released == []
        finally:
            leave.set()
            t.join(5)


class TestOtherStores:
    def test_amazon_does_not_use_the_lock(self, fake_store_lock_redis):
        with store_check_lock("amazon", 5):
            pass
        assert fake_store_lock_redis.created == []

    def test_amazon_is_never_blocked_by_a_busy_ml(self, fake_store_lock_redis):
        with store_check_lock("mercadolivre", 5):
            with store_check_lock("amazon", 0):
                pass

    def test_unknown_or_missing_store_passes_through(self, fake_store_lock_redis):
        with store_check_lock(None, 5):
            pass
        with store_check_lock("shopee", 5):
            pass
        assert fake_store_lock_redis.created == []


class TestRedisDown:
    def test_continues_without_lock_and_logs_warning(self, fake_store_lock_redis, caplog):
        fake_store_lock_redis.acquire_error = ConnectionError("redis fora")
        ran = []
        with caplog.at_level("WARNING", logger="execution.store_lock"):
            with store_check_lock("mercadolivre", 5):
                ran.append(True)
        assert ran == [True]
        assert any("SEM trava" in r.message for r in caplog.records)

    def test_body_exception_still_propagates_when_redis_is_down(self, fake_store_lock_redis):
        fake_store_lock_redis.acquire_error = ConnectionError("redis fora")
        with pytest.raises(ValueError):
            with store_check_lock("mercadolivre", 5):
                raise ValueError("boom")

    def test_release_failure_is_swallowed(self, fake_store_lock_redis, monkeypatch):
        # a trava expirou durante a checagem longa: release() levanta, mas o resultado não se perde
        from execution import store_lock

        class ExpiredLock:
            def acquire(self, blocking=True):
                return True

            def release(self):
                raise RuntimeError("Cannot release an unlocked lock")

        monkeypatch.setattr(
            store_lock.redis_client, "lock", lambda *a, **k: ExpiredLock(), raising=False
        )
        with store_check_lock("mercadolivre", 1):
            pass
