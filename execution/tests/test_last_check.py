"""
Unit tests for db_client.mark_product_checked.

O banco (Prisma) é mockado: o que se verifica é o `data` enviado ao update —
sucesso grava lastCheckedAt, falha não mexe nele.
"""

from unittest.mock import MagicMock, patch

import pytest

from execution import db_client
from execution.db_client import mark_product_checked


@pytest.fixture
def fake_db():
    with patch.object(db_client, "db") as mock_db, patch.object(db_client, "connect_db"):
        yield mock_db


def _update_data(fake_db) -> dict:
    fake_db.product.update.assert_called_once()
    call = fake_db.product.update.call_args
    assert call.kwargs["where"] == {"id": "prod-1"}
    return call.kwargs["data"]


class TestMarkProductChecked:
    @pytest.mark.parametrize("status", ["ok", "out_of_stock", "no_offer"])
    def test_success_sets_checked_and_attempt_and_clears_error(self, fake_db, status):
        mark_product_checked("prod-1", status)
        data = _update_data(fake_db)
        assert data["lastCheckStatus"] == status
        assert data["lastCheckError"] is None
        assert data["lastCheckedAt"] is not None
        assert data["lastCheckedAt"] == data["lastAttemptAt"]

    @pytest.mark.parametrize(
        "status, error", [("error", "scrape_failed"), ("blocked", "captcha")]
    )
    def test_failure_sets_only_attempt_and_keeps_last_checked(self, fake_db, status, error):
        mark_product_checked("prod-1", status, error)
        data = _update_data(fake_db)
        assert data["lastCheckStatus"] == status
        assert data["lastCheckError"] == error
        assert data["lastAttemptAt"] is not None
        assert "lastCheckedAt" not in data

    def test_returns_updated_product(self, fake_db):
        updated = MagicMock()
        fake_db.product.update.return_value = updated
        assert mark_product_checked("prod-1", "ok") is updated

    def test_database_error_is_logged_not_raised(self, fake_db):
        fake_db.product.update.side_effect = RuntimeError("conexão perdida")
        assert mark_product_checked("prod-1", "ok") is None

    def test_connection_error_is_logged_not_raised(self):
        with patch.object(db_client, "connect_db", side_effect=RuntimeError("sem banco")):
            assert mark_product_checked("prod-1", "ok") is None
