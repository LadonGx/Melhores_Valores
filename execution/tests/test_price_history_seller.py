"""
Unit tests for the seller of each price reading (Amazon x third parties) in db_client.

O banco (Prisma) é mockado: verifica-se a regra de deduplicação de add_price_history e o
SQL das estatísticas (preços de terceiros fora enquanto houver preço da própria loja).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from execution import db_client
from execution.db_client import add_price_history, get_group_price_stats, get_price_stats


@pytest.fixture
def fake_db():
    with patch.object(db_client, "db") as mock_db, patch.object(db_client, "connect_db"):
        yield mock_db


def _last_entry(price=70.0, in_stock=True, seller_type="amazon", seller_name=None):
    return SimpleNamespace(
        price=price,
        inStock=in_stock,
        sellerType=seller_type,
        sellerName=seller_name,
        scrapedAt=datetime.now(timezone.utc),  # mesmo dia: só grava se algo mudou
    )


class TestAddPriceHistoryDedup:
    def test_same_price_and_seller_same_day_is_deduplicated(self, fake_db):
        fake_db.pricehistory.find_first.return_value = _last_entry()
        assert add_price_history("prod-1", 70.0, True, "amazon", None) is None
        fake_db.pricehistory.create.assert_not_called()

    def test_seller_change_with_same_price_is_recorded(self, fake_db):
        """Esgotou na Amazon e um terceiro passou a vender pelo mesmo valor: é outro ponto."""
        fake_db.pricehistory.find_first.return_value = _last_entry()
        add_price_history("prod-1", 70.0, True, "third_party", "Sebo X")
        data = fake_db.pricehistory.create.call_args.kwargs["data"]
        assert data["sellerType"] == "third_party"
        assert data["sellerName"] == "Sebo X"
        assert data["price"] == 70.0

    def test_third_party_name_change_is_recorded(self, fake_db):
        fake_db.pricehistory.find_first.return_value = _last_entry(
            seller_type="third_party", seller_name="Sebo X"
        )
        add_price_history("prod-1", 70.0, True, "third_party", "Sebo Y")
        fake_db.pricehistory.create.assert_called_once()

    def test_default_seller_is_unknown(self, fake_db):
        fake_db.pricehistory.find_first.return_value = None
        add_price_history("prod-1", 70.0)
        data = fake_db.pricehistory.create.call_args.kwargs["data"]
        assert data["sellerType"] is None
        assert data["sellerName"] is None


class TestStatsExcludeThirdParty:
    def test_product_stats_use_own_prices_with_fallback(self, fake_db):
        fake_db.pricehistory.find_first.return_value = None
        fake_db.query_raw.return_value = [
            {"lowest": 70.0, "average": 70.0, "median": 70.0, "excluded": 2}
        ]
        stats = get_price_stats("prod-1")
        sql = fake_db.query_raw.call_args.args[0]
        assert "\"sellerType\" NOT IN ('third_party', 'third_party_from')" in sql
        assert "NOT EXISTS (SELECT 1 FROM own)" in sql  # anúncio só de terceiros usa todos
        assert "FROM base" in sql
        assert stats["third_party_excluded"] is True

    def test_nothing_excluded_is_reported(self, fake_db):
        fake_db.pricehistory.find_first.return_value = None
        fake_db.query_raw.return_value = [
            {"lowest": 70.0, "average": 70.0, "median": 70.0, "excluded": 0}
        ]
        assert get_price_stats("prod-1")["third_party_excluded"] is False

    def test_group_stats_use_the_same_rule(self, fake_db):
        fake_db.query_raw.return_value = [{"lowest": 70.0, "median": 70.0}]
        get_group_price_stats(["p1", "p2"])
        sql = fake_db.query_raw.call_args.args[0]
        assert '"productId" IN ($1, $2)' in sql
        assert "NOT EXISTS (SELECT 1 FROM own)" in sql
