"""
Testes da medição das checagens (CheckAttempt), do formato do anúncio e da troca de
anúncio dentro de um grupo — a parte de banco (db_client) e de API (web_server).

O Prisma é substituído por um MagicMock por teste, como no resto da suíte.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from execution import db_client
from execution.store_lock import StoreBusyError
from execution.web_server import (
    _build_store_stats,
    add_group_products,
    AddGroupProductsRequest,
    list_products,
    refresh_product_price,
    stores_stats,
)


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(db_client, "db", db)
    monkeypatch.setattr(db_client, "connect_db", lambda: None)
    return db


# ─── db_client.record_check_attempt ───────────────────────────────────────────

class TestRecordCheckAttempt:
    def test_creates_one_row_with_all_fields(self, fake_db):
        db_client.record_check_attempt(
            "p1", "mercadolivre", "blocked",
            block_category="login_wall", level=2, duration_ms=29123.7, trigger="scheduled",
        )
        data = fake_db.checkattempt.create.call_args.kwargs["data"]
        assert data == {
            "productId": "p1",
            "store": "mercadolivre",
            "status": "blocked",
            "blockCategory": "login_wall",
            "error": None,
            "level": 2,
            "durationMs": 29123,
            "trigger": "scheduled",
        }

    def test_defaults(self, fake_db):
        db_client.record_check_attempt("p1", "amazon", "ok")
        data = fake_db.checkattempt.create.call_args.kwargs["data"]
        assert data["trigger"] == "scheduled"
        assert data["level"] is None and data["durationMs"] is None

    def test_never_raises(self, fake_db):
        fake_db.checkattempt.create.side_effect = RuntimeError("db fora")
        db_client.record_check_attempt("p1", "amazon", "error", error="exception")  # não levanta


# ─── db_client.set_product_format ─────────────────────────────────────────────

class TestSetProductFormat:
    @pytest.mark.parametrize("value", ["ebook_kindle", "physical", None])
    def test_saves_known_values(self, fake_db, value):
        db_client.set_product_format("p1", value)
        fake_db.product.update.assert_called_once_with(where={"id": "p1"}, data={"format": value})

    def test_unknown_value_becomes_null(self, fake_db):
        db_client.set_product_format("p1", "audiobook")
        assert fake_db.product.update.call_args.kwargs["data"] == {"format": None}

    def test_never_raises(self, fake_db):
        fake_db.product.update.side_effect = RuntimeError("db fora")
        db_client.set_product_format("p1", "physical")


# ─── db_client.get_check_attempt_counts ───────────────────────────────────────

class TestCheckAttemptCounts:
    def test_query_uses_days_and_brasilia_hour(self, fake_db):
        fake_db.query_raw.return_value = [
            {"store": "mercadolivre", "status": "ok", "block_category": None,
             "trigger": "scheduled", "hour": 9, "count": 9},
        ]
        rows = db_client.get_check_attempt_counts(7)
        sql, *params = fake_db.query_raw.call_args.args
        assert params == [7]
        assert "America/Sao_Paulo" in sql
        assert '"trigger" =' not in sql
        assert rows == [{"store": "mercadolivre", "status": "ok", "block_category": None,
                         "trigger": "scheduled", "hour": 9, "count": 9}]

    def test_trigger_filter(self, fake_db):
        fake_db.query_raw.return_value = []
        db_client.get_check_attempt_counts(3, "scheduled")
        sql, *params = fake_db.query_raw.call_args.args
        assert params == [3, "scheduled"]
        assert '"trigger" = $2' in sql


# ─── GET /stores/stats ────────────────────────────────────────────────────────

_LABELS = {"amazon": "Amazon", "mercadolivre": "Mercado Livre"}


def _row(store, status, hour, count, block=None, trigger="scheduled"):
    return {"store": store, "status": status, "block_category": block,
            "trigger": trigger, "hour": hour, "count": count}


class TestStoreStats:
    def test_baseline_day_of_11_11(self):
        """09:00 → 9 de 9 ok; 15:00 → 9 de 9 login_wall; ~19:00 botão → ok."""
        rows = [
            _row("mercadolivre", "ok", 9, 9),
            _row("mercadolivre", "blocked", 15, 9, block="login_wall"),
            _row("mercadolivre", "ok", 19, 1, trigger="manual"),
        ]
        stats = {s["store"]: s for s in _build_store_stats(rows, _LABELS)}
        ml = stats["mercadolivre"]
        assert ml["label"] == "Mercado Livre"
        assert ml["total"] == 19
        assert ml["successes"] == 10
        assert ml["success_rate"] == round(10 / 19, 4)
        assert ml["by_status"] == {"ok": 10, "blocked": 9}
        assert ml["by_block_category"] == {"login_wall": 9}
        assert ml["by_trigger"] == {"scheduled": 18, "manual": 1}
        assert len(ml["by_hour"]) == 24
        assert ml["by_hour"][9] == {"hour": 9, "total": 9, "successes": 9, "success_rate": 1.0}
        assert ml["by_hour"][15] == {"hour": 15, "total": 9, "successes": 0, "success_rate": 0.0}
        assert ml["by_hour"][0] == {"hour": 0, "total": 0, "successes": 0, "success_rate": None}

    def test_out_of_stock_and_no_offer_count_as_success(self):
        rows = [
            _row("amazon", "out_of_stock", 6, 1),
            _row("amazon", "no_offer", 6, 1),
            _row("amazon", "error", 6, 2),
        ]
        [amazon] = [s for s in _build_store_stats(rows, _LABELS) if s["store"] == "amazon"]
        assert amazon["successes"] == 2
        assert amazon["success_rate"] == 0.5
        assert amazon["by_block_category"] == {}

    def test_known_stores_always_listed_and_unknown_store_appended(self):
        stats = _build_store_stats([_row("magalu", "ok", 1, 1)], _LABELS)
        by_store = {s["store"]: s for s in stats}
        assert set(by_store) == {"amazon", "mercadolivre", "magalu"}
        assert by_store["amazon"]["total"] == 0
        assert by_store["amazon"]["success_rate"] is None
        assert by_store["magalu"]["label"] == "magalu"

    def test_endpoint_shape(self):
        with patch("execution.web_server.get_check_attempt_counts",
                   return_value=[_row("mercadolivre", "ok", 9, 3)]) as counts:
            body = asyncio.run(stores_stats(days=3, trigger="scheduled"))
        counts.assert_called_once_with(3, "scheduled")
        assert body["days"] == 3
        assert body["trigger"] == "scheduled"
        assert body["timezone"] == "America/Sao_Paulo"
        assert datetime.fromisoformat(body["since"]) < datetime.now(timezone.utc)
        ml = next(s for s in body["stores"] if s["store"] == "mercadolivre")
        assert ml["success_rate"] == 1.0


# ─── GET /products: formato ───────────────────────────────────────────────────

def test_products_expose_format():
    product = MagicMock()
    product.history = []
    product.format = "ebook_kindle"
    product.lastCheckedAt = product.lastAttemptAt = None
    product.createdAt = product.updatedAt = datetime(2026, 11, 1, tzinfo=timezone.utc)
    with patch("execution.web_server.get_all_products", return_value=[product]):
        [item] = asyncio.run(list_products())["products"]
    assert item["format"] == "ebook_kindle"


# ─── POST /product/{id}/refresh: Mercado Livre ocupado ────────────────────────

def test_refresh_reports_busy_and_passes_manual_trigger():
    product = MagicMock(url="https://www.mercadolivre.com.br/x/p/MLB1", store="mercadolivre")
    with patch("execution.web_server.get_product_by_id", return_value=product), \
         patch("execution.web_server.run_price_pipeline", side_effect=StoreBusyError()) as pipeline:
        response = asyncio.run(refresh_product_price("prod-1"))
    assert pipeline.call_args.kwargs["trigger"] == "manual"
    assert response["status"] == "error"
    assert response["reason"] == "busy"


# ─── POST /groups/{id}/products ───────────────────────────────────────────────

def _group(product_ids=("p1", "p2")):
    return SimpleNamespace(
        id="g1", name="Ritmo da Guerra",
        items=[SimpleNamespace(productId=pid) for pid in product_ids],
        createdAt=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
    )


class TestAddProductsToGroup:
    def test_adds_new_listing_keeping_the_group(self, fake_db):
        fake_db.productgroup.find_unique.return_value = _group()
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p3")]
        fake_db.productgroupitem.find_many.return_value = []
        fake_db.productgroup.update.return_value = _group(("p1", "p2", "p3"))

        result = db_client.add_products_to_group("g1", ["p3", "p3"])

        data = fake_db.productgroup.update.call_args.kwargs["data"]
        assert data == {"items": {"create": [{"product": {"connect": {"id": "p3"}}}]}}
        assert result["productIds"] == ["p1", "p2", "p3"]

    def test_listing_already_in_this_group_is_ignored(self, fake_db):
        fake_db.productgroup.find_unique.return_value = _group()
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p1")]
        result = db_client.add_products_to_group("g1", ["p1"])
        fake_db.productgroup.update.assert_not_called()
        assert result["productIds"] == ["p1", "p2"]

    def test_unknown_group(self, fake_db):
        fake_db.productgroup.find_unique.return_value = None
        with pytest.raises(LookupError):
            db_client.add_products_to_group("nao-existe", ["p3"])

    def test_no_valid_listing(self, fake_db):
        fake_db.productgroup.find_unique.return_value = _group()
        fake_db.product.find_many.return_value = []
        with pytest.raises(ValueError):
            db_client.add_products_to_group("g1", ["nao-existe"])

    def test_listing_in_another_group(self, fake_db):
        fake_db.productgroup.find_unique.return_value = _group()
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p9")]
        fake_db.productgroupitem.find_many.return_value = [SimpleNamespace(productId="p9")]
        with pytest.raises(db_client.ProductAlreadyGroupedError):
            db_client.add_products_to_group("g1", ["p9"])

    @pytest.mark.parametrize(
        "error, status",
        [(LookupError("x"), 404), (db_client.ProductAlreadyGroupedError("x"), 409), (ValueError("x"), 422)],
    )
    def test_endpoint_status_codes(self, error, status):
        with patch("execution.web_server.add_products_to_group", side_effect=error):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(add_group_products("g1", AddGroupProductsRequest(product_ids=["p3"])))
        assert exc.value.status_code == status
