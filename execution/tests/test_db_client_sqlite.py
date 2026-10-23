"""
Testes do db_client contra um banco SQLite real (arquivo em tmp_path).

Cobrem principalmente o que mudou na troca Postgres/Prisma → SQLite:
deduplicação por dia, estatísticas (mediana), ordem de NULLs, cascata no
delete, datas com fuso e escrita concorrente entre threads.
"""

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from execution import db_client
from execution.db_schema import MIGRATIONS


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_client, "DB_PATH", tmp_path / "test.db")
    yield db_client
    db_client.close_db()


def _set_scraped_at(entry_id: str, when: datetime) -> None:
    conn = db_client.connect_db()
    with conn:
        conn.execute("UPDATE PriceHistory SET scrapedAt = ? WHERE id = ?", (db_client._iso(when), entry_id))


def _product(url="https://www.amazon.com.br/dp/X1", name="Produto Teste"):
    return db_client.get_or_create_product(url=url, name=name, store="amazon")


class TestSchema:
    def test_migrations_set_user_version(self, tmp_path):
        conn = db_client.connect_db()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

    def test_reopening_existing_database_keeps_data(self):
        product = _product()
        db_client.close_db()
        assert db_client.get_product_by_id(product.id) == product

    def test_wal_and_foreign_keys_enabled(self):
        conn = db_client.connect_db()
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


class TestProduct:
    def test_create_returns_model_with_defaults_and_aware_dates(self):
        product = _product()
        assert product.store == "amazon"
        assert product.status == "active"
        assert product.history is None
        assert product.createdAt.tzinfo is not None
        assert product.createdAt == product.updatedAt

    def test_get_or_create_is_idempotent(self):
        first = _product()
        second = _product(name="Outro Nome")
        assert first.id == second.id
        assert second.name == "Produto Teste"  # nome bom não é sobrescrito

    def test_garbage_name_is_replaced_by_real_name(self):
        _product(name="Rate Limited")
        updated = db_client.get_or_create_product(
            url="https://www.amazon.com.br/dp/X1", name="iPhone 15", image_url="https://img/1.jpg"
        )
        assert updated.name == "iPhone 15"
        assert updated.imageUrl == "https://img/1.jpg"

    def test_store_defaults_to_unknown(self):
        product = db_client.get_or_create_product(url="https://x.com/p")
        assert product.store == "unknown"

    def test_unique_url_constraint(self):
        _product()
        conn = db_client.connect_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO Product (id, url, store, createdAt, updatedAt) VALUES ('x', ?, 'amazon', '', '')",
                ("https://www.amazon.com.br/dp/X1",),
            )

    def test_update_name_and_status_bump_updated_at(self):
        product = _product()
        old = "2025-01-01T00:00:00.000000+00:00"

        def _age_product():
            conn = db_client.connect_db()
            with conn:
                conn.execute("UPDATE Product SET updatedAt = ? WHERE id = ?", (old, product.id))

        _age_product()
        renamed = db_client.update_product_name(product.id, "Novo Nome")
        _age_product()
        paused = db_client.update_product_status(product.id, "paused")

        assert renamed.name == "Novo Nome"
        assert paused.status == "paused"
        assert paused.name == "Novo Nome"
        for updated in (renamed, paused):
            assert updated.updatedAt > datetime.fromisoformat(old)
            assert updated.createdAt == product.createdAt

    def test_update_missing_product_returns_none(self):
        assert db_client.update_product_name("nao-existe", "Nome") is None
        assert db_client.update_product_status("nao-existe", "paused") is None

    def test_get_missing_product_returns_none(self):
        assert db_client.get_product_by_id("nao-existe") is None

    def test_delete_cascades_history(self):
        product = _product()
        db_client.add_price_history(product.id, 100.0)
        assert db_client.delete_product(product.id) is True
        assert db_client.get_product_by_id(product.id) is None
        count = db_client.connect_db().execute("SELECT COUNT(*) FROM PriceHistory").fetchone()[0]
        assert count == 0

    def test_delete_missing_product_returns_false(self):
        assert db_client.delete_product("nao-existe") is False


class TestPriceHistory:
    def test_first_entry_is_inserted(self):
        product = _product()
        entry = db_client.add_price_history(product.id, 100.0)
        assert entry is not None
        assert entry.price == 100.0
        assert entry.inStock is True
        assert entry.scrapedAt.tzinfo is not None

    def test_unchanged_price_same_day_is_deduplicated(self):
        product = _product()
        db_client.add_price_history(product.id, 100.0)
        assert db_client.add_price_history(product.id, 100.0) is None

    def test_changed_price_same_day_is_inserted(self):
        product = _product()
        db_client.add_price_history(product.id, 100.0)
        assert db_client.add_price_history(product.id, 90.0) is not None

    def test_changed_stock_same_day_is_inserted(self):
        product = _product()
        db_client.add_price_history(product.id, None, in_stock=False)
        assert db_client.add_price_history(product.id, None, in_stock=True) is not None

    def test_unchanged_price_on_previous_day_is_inserted(self):
        product = _product()
        first = db_client.add_price_history(product.id, 100.0)
        _set_scraped_at(first.id, datetime.now(timezone.utc) - timedelta(days=1))
        assert db_client.add_price_history(product.id, 100.0) is not None

    def test_latest_entry_and_last_valid_price(self):
        product = _product()
        old = db_client.add_price_history(product.id, 120.0)
        _set_scraped_at(old.id, datetime.now(timezone.utc) - timedelta(days=1))
        db_client.add_price_history(product.id, None, in_stock=False)

        assert db_client.get_latest_price_entry(product.id).inStock is False
        # sanity check ignora a entrada fora de estoque
        assert db_client.get_last_valid_price_for_url(product.url) == 120.0

    def test_last_valid_price_for_unknown_url_is_none(self):
        assert db_client.get_last_valid_price_for_url("https://nao-existe") is None

    def test_chart_respects_window_and_is_ascending(self):
        product = _product()
        ages = {150.0: 40, 140.0: 10, 130.0: 0}
        for price, days_ago in ages.items():
            entry = db_client.add_price_history(product.id, price)
            _set_scraped_at(entry.id, datetime.now(timezone.utc) - timedelta(days=days_ago, minutes=1))

        last_30 = db_client.get_price_history_chart(product.id, 30)
        assert [p.price for p in last_30] == [140.0, 130.0]
        everything = db_client.get_price_history_chart(product.id, None)
        assert [p.price for p in everything] == [150.0, 140.0, 130.0]

    def test_history_page_is_descending_with_total(self):
        product = _product()
        for i in range(5):
            entry = db_client.add_price_history(product.id, 100.0 + i)
            _set_scraped_at(entry.id, datetime(2026, 1, 1 + i, tzinfo=timezone.utc))

        entries, total = db_client.get_price_history_page(product.id, page=2, limit=2)
        assert total == 5
        assert [e.price for e in entries] == [102.0, 101.0]


class TestStats:
    def _history(self, product_id, prices):
        for i, price in enumerate(prices):
            entry = db_client.add_price_history(product_id, price, in_stock=price is not None)
            _set_scraped_at(entry.id, datetime(2026, 1, 1 + i, tzinfo=timezone.utc))

    def test_price_stats(self):
        product = _product()
        self._history(product.id, [400.0, 100.0, None, 300.0, 200.0])
        assert db_client.get_price_stats(product.id) == {
            "current_price": 200.0,
            "lowest_price": 100.0,
            "average_price": 250.0,
            "median_price": 250.0,  # par: média dos dois centrais, como percentile_cont(0.5)
        }

    def test_price_stats_without_history(self):
        product = _product()
        assert db_client.get_price_stats(product.id) == {
            "current_price": None,
            "lowest_price": None,
            "average_price": None,
            "median_price": None,
        }

    def test_average_is_rounded(self):
        product = _product()
        self._history(product.id, [10.0, 10.0, 10.01])
        assert db_client.get_price_stats(product.id)["average_price"] == 10.0

    def test_group_stats_use_pooled_median(self):
        a = _product(url="https://a")
        b = _product(url="https://b")
        self._history(a.id, [10.0, 20.0, 30.0])
        self._history(b.id, [100.0])
        # mediana do conjunto [10, 20, 30, 100] = 25; mediana das medianas seria 60
        assert db_client.get_group_price_stats([a.id, b.id]) == {
            "lowest_price": 10.0,
            "median_price": 25.0,
        }

    def test_group_stats_empty_ids(self):
        assert db_client.get_group_price_stats([]) == {"lowest_price": None, "median_price": None}


class TestProductListing:
    def test_get_all_products_includes_only_latest_entry_newest_product_first(self):
        old = _product(url="https://old")
        new = _product(url="https://new")
        conn = db_client.connect_db()
        with conn:
            conn.execute("UPDATE Product SET createdAt = ? WHERE id = ?", ("2025-01-01T00:00:00.000000+00:00", old.id))
        first = db_client.add_price_history(old.id, 100.0)
        _set_scraped_at(first.id, datetime(2026, 1, 1, tzinfo=timezone.utc))
        db_client.add_price_history(old.id, 90.0)

        products = db_client.get_all_products()
        assert [p.id for p in products] == [new.id, old.id]
        assert products[0].history == []
        assert [h.price for h in products[1].history] == [90.0]

    def test_get_products_with_history_is_complete_and_descending(self):
        product = _product()
        for i, price in enumerate([100.0, 90.0, 80.0]):
            entry = db_client.add_price_history(product.id, price)
            _set_scraped_at(entry.id, datetime(2026, 1, 1 + i, tzinfo=timezone.utc))

        [listed] = db_client.get_products_with_history()
        assert [h.price for h in listed.history] == [80.0, 90.0, 100.0]


class TestSearchResults:
    def test_results_ordered_by_price_with_nulls_last(self):
        results = [
            {"store": "amazon", "title": "Sem preço", "price": None, "product_url": "https://1"},
            {"store": "amazon", "title": "Caro", "price": 300.0, "product_url": "https://2"},
            {"store": "mercadolivre", "title": "Barato", "price": 100.0, "product_url": "https://3",
             "rating": 4.5, "review_count": 10},
        ]
        assert db_client.save_search_results("s1", "iphone", results) == 3

        found = db_client.get_search_results("s1")
        assert [r.title for r in found] == ["Barato", "Caro", "Sem preço"]
        assert found[0].currency == "BRL"
        assert found[0].review_count == 10

    def test_invalid_item_is_skipped(self):
        results = [
            {"store": "amazon", "title": "Ok", "product_url": "https://1"},
            {"store": "amazon", "product_url": "https://2"},  # sem title
        ]
        assert db_client.save_search_results("s1", "q", results) == 1

    def test_model_dump_json_serializes_dates(self):
        db_client.save_search_results("s1", "q", [{"store": "amazon", "title": "Ok", "product_url": "https://1"}])
        dumped = db_client.get_search_results("s1")[0].model_dump(mode="json")
        assert isinstance(dumped["found_at"], str)
        assert dumped["found_at"].endswith("Z") or dumped["found_at"].endswith("+00:00")

    def test_unknown_search_returns_empty(self):
        assert db_client.get_search_results("nao-existe") == []


class TestMigrations:
    def test_v1_database_is_upgraded_keeping_data(self, tmp_path):
        """Banco criado por uma versão antiga do app (só a v1) recebe a v2 ao abrir."""
        db_client.close_db()
        path = tmp_path / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
        conn.execute(
            "INSERT INTO Product (id, url, store, createdAt, updatedAt) VALUES ('p1', 'https://old', 'amazon', ?, ?)",
            ("2026-01-01T00:00:00.000000+00:00", "2026-01-01T00:00:00.000000+00:00"),
        )
        conn.commit()
        conn.close()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(db_client, "DB_PATH", path)
            upgraded = db_client.connect_db()
            assert upgraded.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
            assert db_client.get_product_by_id("p1").url == "https://old"
            assert db_client.get_last_full_check() is None
            db_client.close_db()


class TestBulkImport:
    def _models(self):
        from execution.models import PriceHistory, Product

        when = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        product = Product(id="p1", url="https://a", store="amazon", createdAt=when, updatedAt=when)
        history = [PriceHistory(id="h1", price=10.0, scrapedAt=when, productId="p1")]
        return [product], history

    def test_import_into_empty_database(self):
        assert db_client.is_empty() is True
        products, history = self._models()
        assert db_client.bulk_import(products, history) == {"products": 1, "history": 1, "search_results": 0}
        assert db_client.is_empty() is False
        assert db_client.get_latest_price_entry("p1").id == "h1"

    def test_refuses_database_with_data(self):
        _product(url="https://ja-existe")
        products, history = self._models()
        with pytest.raises(ValueError, match="já tem dados"):
            db_client.bulk_import(products, history)
        assert db_client.get_product_by_id("p1") is None

    def test_is_all_or_nothing(self):
        from execution.models import PriceHistory

        products, history = self._models()
        orphan = PriceHistory(id="h2", price=1.0, scrapedAt=history[0].scrapedAt, productId="nao-existe")
        with pytest.raises(sqlite3.IntegrityError):
            db_client.bulk_import(products, history + [orphan])
        assert db_client.is_empty() is True


class TestProductGroups:
    def _three_products(self):
        return [_product(url=f"https://g/{i}", name=f"Livro {i}").id for i in range(3)]

    def test_create_and_list_keep_member_order(self):
        a, b, c = self._three_products()
        group = db_client.create_group("  Livros  ", [c, a, b])
        assert group.name == "Livros"
        assert group.productIds == [c, a, b]
        assert group.createdAt.tzinfo is not None
        assert db_client.list_groups() == [group]

    def test_unknown_and_repeated_products_are_ignored(self):
        a, b, _ = self._three_products()
        group = db_client.create_group("G", [a, "nao-existe", a, b])
        assert group.productIds == [a, b]

    def test_group_needs_two_existing_products_and_a_name(self):
        a, b, _ = self._three_products()
        with pytest.raises(ValueError, match="ao menos 2"):
            db_client.create_group("G", [a, "nao-existe"])
        with pytest.raises(ValueError, match="nome"):
            db_client.create_group("   ", [a, b])
        assert db_client.list_groups() == []

    def test_rename_and_change_members(self):
        a, b, c = self._three_products()
        group = db_client.create_group("G", [a, b])
        updated = db_client.update_group(group.id, name="Novo nome", product_ids=[b, c])
        assert updated.name == "Novo nome" and updated.productIds == [b, c]

    def test_update_to_less_than_two_dissolves_group(self):
        a, b, _ = self._three_products()
        group = db_client.create_group("G", [a, b])
        assert db_client.update_group(group.id, product_ids=[a]) is None
        assert db_client.list_groups() == []
        assert db_client.get_product_by_id(a) is not None  # produtos continuam

    def test_update_missing_group_returns_none(self):
        assert db_client.update_group("nao-existe", name="X") is None

    def test_delete_group_keeps_products(self):
        a, b, _ = self._three_products()
        group = db_client.create_group("G", [a, b])
        assert db_client.delete_group(group.id) is True
        assert db_client.delete_group(group.id) is False
        assert db_client.get_product_by_id(a) is not None

    def test_deleting_a_product_updates_groups(self):
        a, b, c = self._three_products()
        pair = db_client.create_group("Par", [a, b])
        trio = db_client.create_group("Trio", [a, b, c])
        db_client.delete_product(a)
        groups = {g.name: g for g in db_client.list_groups()}
        assert "Par" not in groups                      # ficou com 1 anúncio: desfeito
        assert groups["Trio"].productIds == [b, c]      # perdeu só o excluído
        assert pair.id != trio.id

    def test_import_from_localstorage_is_idempotent(self):
        a, b, c = self._three_products()
        legacy = [
            {"id": "g1", "name": "Do navegador", "productIds": [a, b], "createdAt": "2026-09-01T12:00:00.000Z"},
            {"id": "g2", "name": "Só um válido", "productIds": [c, "apagado"], "createdAt": "2026-09-02T12:00:00.000Z"},
            {"name": "sem id"},
        ]
        assert db_client.import_groups(legacy) == {"imported": 1, "skipped": 2}
        assert db_client.import_groups(legacy) == {"imported": 0, "skipped": 3}
        [group] = db_client.list_groups()
        assert group.id == "g1" and group.name == "Do navegador"
        assert group.createdAt == datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    def test_v2_database_is_upgraded_to_v3(self, tmp_path):
        db_client.close_db()
        path = tmp_path / "v2.db"
        conn = sqlite3.connect(path)
        for version, sql in enumerate(MIGRATIONS[:2], start=1):
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
        conn.close()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(db_client, "DB_PATH", path)
            assert db_client.connect_db().execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
            assert db_client.list_groups() == []
            db_client.close_db()


class TestAppMeta:
    def test_last_full_check_round_trip_and_upsert(self):
        assert db_client.get_last_full_check() is None

        first = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
        db_client.set_last_full_check(first)
        assert db_client.get_last_full_check() == first

        later = first + timedelta(hours=6)
        db_client.set_last_full_check(later)
        assert db_client.get_last_full_check() == later

    def test_last_full_check_is_stored_in_utc(self):
        brt = timezone(timedelta(hours=-3))
        db_client.set_last_full_check(datetime(2026, 10, 21, 6, 0, tzinfo=brt))
        stored = db_client.get_last_full_check()
        assert stored == datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
        assert stored.utcoffset() == timedelta(0)


class TestConcurrency:
    def test_concurrent_writers_from_threads(self):
        errors: list[Exception] = []

        def worker(n: int):
            try:
                for i in range(20):
                    product = db_client.get_or_create_product(url=f"https://p/{i % 5}", name=f"Produto {i % 5}")
                    db_client.add_price_history(product.id, float(n * 100 + i))
            except Exception as e:  # pragma: no cover - só falha se houver lock/concorrência
                errors.append(e)
            finally:
                db_client.close_db()

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(db_client.get_all_products()) == 5
