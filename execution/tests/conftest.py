"""
Pytest configuration for unit tests.

Mocks heavy optional dependencies (playwright, celery, redis) so the
adapter and pipeline tests can run locally without Docker.
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock

# Nenhum teste pode tocar a pasta de dados real do usuário: settings.py lê esta
# variável no import, então ela precisa estar definida antes de qualquer import
# de `execution`. Testes do db_client usam um banco próprio em tmp_path.
os.environ["MV_DATA_DIR"] = tempfile.mkdtemp(prefix="mv-tests-")

# Stub playwright before any module imports it
playwright_stub = MagicMock()
sys.modules["playwright"] = playwright_stub
sys.modules["playwright.sync_api"] = playwright_stub

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
