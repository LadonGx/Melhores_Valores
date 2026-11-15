"""
Pytest configuration for unit tests.

Mocks heavy optional dependencies (playwright, prisma, celery, redis) so the
adapter and pipeline tests can run locally without Docker.
"""

import sys
from unittest.mock import MagicMock

# Stub playwright before any module imports it
playwright_stub = MagicMock()
sys.modules["playwright"] = playwright_stub
sys.modules["playwright.sync_api"] = playwright_stub

# Stub prisma (DB layer) — DB calls are mocked per-test anyway
prisma_stub = MagicMock()
sys.modules["prisma"] = prisma_stub
sys.modules["prisma.models"] = prisma_stub
# prisma.errors precisa de classes de exceção de verdade (usadas em "except")
prisma_errors_stub = MagicMock()
prisma_errors_stub.UniqueViolationError = type("UniqueViolationError", (Exception,), {})
sys.modules["prisma.errors"] = prisma_errors_stub

# Stub celery and redis (not needed for unit tests)
celery_stub = MagicMock()
sys.modules["celery"] = celery_stub
sys.modules["celery.schedules"] = celery_stub

# Stub dotenv
dotenv_stub = MagicMock()
sys.modules["dotenv"] = dotenv_stub

# Stub httpx (used in base_scraper and firecrawl_api, mocked per-test)
httpx_stub = MagicMock()
sys.modules["httpx"] = httpx_stub


# ── Saúde das lojas: nunca escrever no Redis real durante os testes ──────────
import pytest  # noqa: E402


class FakeRedisHash:
    """Redis mínimo em memória (hset/hgetall) para execution.store_health."""

    def __init__(self):
        self.data: dict[str, dict[str, str]] = {}

    def hset(self, key, mapping):
        self.data.setdefault(key, {}).update(mapping)

    def hgetall(self, key):
        return dict(self.data.get(key, {}))


@pytest.fixture(autouse=True)
def fake_store_health_redis(monkeypatch):
    from execution import store_health

    fake = FakeRedisHash()
    monkeypatch.setattr(store_health, "redis_client", fake)
    return fake


# ── Trava por loja: nunca falar com o Redis real durante os testes ───────────
import threading  # noqa: E402


class FakeRedisLock:
    """Lock do redis-py em memória: acquire(blocking) respeita `blocking_timeout`."""

    def __init__(self, owner: "FakeRedisLocks", name, timeout, blocking_timeout):
        self.owner = owner
        self.name = name
        self.timeout = timeout
        self.blocking_timeout = blocking_timeout
        self._lock = owner.locks.setdefault(name, threading.Lock())
        self._held = False

    def acquire(self, blocking=True):
        if self.owner.acquire_error:
            raise self.owner.acquire_error
        wait = self.blocking_timeout if blocking else 0
        self._held = self._lock.acquire(timeout=wait if wait is not None else -1)
        if self._held:
            self.owner.acquired.append(self.name)
        return self._held

    def release(self):
        if not self._held:
            raise RuntimeError("lock não adquirido")
        self._held = False
        self.owner.released.append(self.name)
        self._lock.release()


class FakeRedisLocks:
    """Redis mínimo em memória com `.lock(...)` para execution.store_lock."""

    def __init__(self):
        self.locks: dict[str, threading.Lock] = {}
        self.created: list[dict] = []
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.acquire_error: Exception | None = None

    def lock(self, name, timeout=None, blocking_timeout=None):
        self.created.append({"name": name, "timeout": timeout, "blocking_timeout": blocking_timeout})
        return FakeRedisLock(self, name, timeout, blocking_timeout)


@pytest.fixture(autouse=True)
def fake_store_lock_redis(monkeypatch):
    from execution import store_lock

    fake = FakeRedisLocks()
    monkeypatch.setattr(store_lock, "redis_client", fake)
    return fake
