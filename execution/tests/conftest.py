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
