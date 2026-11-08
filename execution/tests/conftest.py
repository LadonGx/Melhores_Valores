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
