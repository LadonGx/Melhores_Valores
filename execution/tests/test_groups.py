"""
Testes dos grupos de anúncios em db_client (create/remove/prune).

O Prisma é substituído por um MagicMock por teste (como no resto da suíte);
o que se testa aqui são as regras: ids repetidos/inexistentes, mínimo de 2
anúncios e grupo desfeito quando sobra só 1.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from execution import db_client


def _item(product_id):
    return SimpleNamespace(productId=product_id)


def _group(group_id="g1", name="Box Agatha", product_ids=("p1", "p2")):
    return SimpleNamespace(
        id=group_id,
        name=name,
        items=[_item(pid) for pid in product_ids],
        createdAt=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def fake_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(db_client, "db", db)
    monkeypatch.setattr(db_client, "connect_db", lambda: None)
    return db


class TestCreateGroup:
    def test_ignores_duplicated_and_unknown_ids(self, fake_db):
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p1"), SimpleNamespace(id="p2")]
        fake_db.productgroupitem.find_many.return_value = []
        fake_db.productgroup.create.return_value = _group()

        result = db_client.create_group("  Box Agatha  ", ["p1", "p2", "p1", "nao-existe"])

        data = fake_db.productgroup.create.call_args.kwargs["data"]
        assert data["name"] == "Box Agatha"
        assert data["items"]["create"] == [
            {"product": {"connect": {"id": "p1"}}},
            {"product": {"connect": {"id": "p2"}}},
        ]
        assert result == {
            "id": "g1",
            "name": "Box Agatha",
            "productIds": ["p1", "p2"],
            "createdAt": "2026-11-08T12:00:00+00:00",
        }

    def test_requires_at_least_two_valid_products(self, fake_db):
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p1")]
        with pytest.raises(ValueError):
            db_client.create_group("Grupo", ["p1", "nao-existe"])
        fake_db.productgroup.create.assert_not_called()

    def test_requires_a_name(self, fake_db):
        with pytest.raises(ValueError):
            db_client.create_group("   ", ["p1", "p2"])


class TestRemoveProductFromGroup:
    def test_group_with_two_or_more_left_is_returned(self, fake_db):
        fake_db.productgroupitem.find_unique.return_value = _item("p3")
        fake_db.productgroup.find_unique.return_value = _group(product_ids=("p1", "p2"))

        result = db_client.remove_product_from_group("g1", "p3")

        assert result["productIds"] == ["p1", "p2"]
        fake_db.productgroup.delete.assert_not_called()

    def test_group_left_with_one_product_is_dissolved(self, fake_db):
        fake_db.productgroupitem.find_unique.return_value = _item("p2")
        fake_db.productgroup.find_unique.return_value = _group(product_ids=("p1",))

        assert db_client.remove_product_from_group("g1", "p2") is None
        fake_db.productgroup.delete.assert_called_once_with(where={"id": "g1"})

    def test_unknown_item_raises_lookup_error(self, fake_db):
        fake_db.productgroupitem.find_unique.return_value = None
        with pytest.raises(LookupError):
            db_client.remove_product_from_group("g1", "p9")


class TestPruneSmallGroups:
    def test_deletes_only_groups_below_minimum(self, fake_db):
        fake_db.productgroup.find_many.return_value = [
            _group("g1", product_ids=("p1", "p2")),
            _group("g2", product_ids=("p3",)),
            _group("g3", product_ids=()),
        ]
        assert db_client._prune_small_groups() == 2
        fake_db.productgroup.delete_many.assert_called_once_with(where={"id": {"in": ["g2", "g3"]}})

    def test_delete_product_prunes_groups(self, fake_db):
        fake_db.productgroup.find_many.return_value = [_group("g1", product_ids=("p2",))]
        assert db_client.delete_product("p1") is True
        fake_db.productgroup.delete_many.assert_called_once_with(where={"id": {"in": ["g1"]}})


class TestOneGroupPerProduct:
    def test_rejects_products_already_in_another_group(self, fake_db):
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p1"), SimpleNamespace(id="p2")]
        fake_db.productgroupitem.find_many.return_value = [_item("p2")]

        with pytest.raises(db_client.ProductAlreadyGroupedError):
            db_client.create_group("Grupo", ["p1", "p2"])
        fake_db.productgroup.create.assert_not_called()

    def test_race_on_unique_index_becomes_already_grouped(self, fake_db):
        fake_db.product.find_many.return_value = [SimpleNamespace(id="p1"), SimpleNamespace(id="p2")]
        fake_db.productgroupitem.find_many.return_value = []
        fake_db.productgroup.create.side_effect = db_client.UniqueViolationError("unique")

        with pytest.raises(db_client.ProductAlreadyGroupedError):
            db_client.create_group("Grupo", ["p1", "p2"])


class TestGroupRoutes:
    def test_post_group_returns_409_when_product_already_grouped(self, monkeypatch):
        import asyncio
        from fastapi import HTTPException
        from execution import web_server

        def fake_create(name, product_ids):
            raise db_client.ProductAlreadyGroupedError("já agrupado")

        monkeypatch.setattr(web_server, "create_group", fake_create)
        req = web_server.CreateGroupRequest(name="G", product_ids=["p1", "p2"])
        with pytest.raises(HTTPException) as exc:
            asyncio.run(web_server.post_group(req))
        assert exc.value.status_code == 409
        assert exc.value.detail == "já agrupado"
