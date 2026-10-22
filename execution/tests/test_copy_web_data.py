"""
Testes do scripts/copy_web_data.py (cópia dos dados da versão web → SQLite novo).
O Postgres é simulado: o que importa aqui é (1) só leitura na origem, (2) nunca
sobrescrever um destino existente e (3) datas convertidas sem deslocar fuso.
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from execution import db_client

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "copy_web_data.py"
_spec = importlib.util.spec_from_file_location("copy_web_data", SCRIPT)
copy_web_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(copy_web_data)

T0 = datetime(2026, 9, 1, 15, 30, 0, 123000)  # "ingênuo", como o psycopg devolve o timestamp(3) do Prisma


def _raw():
    return {
        "Product": [{"id": "p1", "url": "https://a", "name": "Mouse", "imageUrl": None, "store": "amazon",
                     "status": "active", "createdAt": T0, "updatedAt": T0}],
        "PriceHistory": [
            {"id": "h1", "price": 99.9, "inStock": True, "scrapedAt": T0, "productId": "p1"},
            {"id": "h2", "price": None, "inStock": False, "scrapedAt": T0.replace(day=2), "productId": "p1"},
        ],
        "SearchResult": [{"id": "s1", "search_id": "busca", "query": "mouse", "store": "amazon", "title": "Mouse",
                          "price": 50.0, "currency": "BRL", "image_url": None, "product_url": "https://a",
                          "rating": 4.5, "review_count": 10, "found_at": T0}],
    }


@pytest.fixture(autouse=True)
def restore_db_path(monkeypatch, tmp_path):
    # copy_to_sqlite troca db_client.DB_PATH; o monkeypatch devolve o original no fim
    monkeypatch.setattr(db_client, "DB_PATH", tmp_path / "nao-usado.db")
    yield
    db_client.close_db()


class TestHelpers:
    def test_prisma_only_params_are_removed_from_url(self):
        url = "postgresql://user:pw@localhost:5432/price_tracker?schema=public&sslmode=disable"
        assert copy_web_data.to_libpq_url(url) == "postgresql://user:pw@localhost:5432/price_tracker?sslmode=disable"

    def test_naive_datetimes_are_read_as_utc_not_local_time(self):
        products, history, results = copy_web_data.to_models(_raw())
        assert products[0].createdAt == T0.replace(tzinfo=timezone.utc)
        assert history[0].scrapedAt.utcoffset().total_seconds() == 0
        assert results[0].found_at.tzinfo is timezone.utc


class TestCopyToSqlite:
    def test_copies_everything_preserving_ids_and_dates(self, tmp_path):
        dest = tmp_path / "copia"
        assert copy_web_data.copy_to_sqlite(_raw(), dest) == {"products": 1, "history": 2, "search_results": 1}

        db_client.DB_PATH = dest / "melhores_valores.db"
        [product] = db_client.get_products_with_history()
        assert product.id == "p1" and product.createdAt == T0.replace(tzinfo=timezone.utc)
        assert [h.id for h in product.history] == ["h2", "h1"]
        assert db_client.get_search_results("busca")[0].id == "s1"
        assert db_client.get_price_stats("p1")["lowest_price"] == 99.9

    def test_refuses_existing_destination_file(self, tmp_path):
        dest = tmp_path / "copia"
        dest.mkdir()
        (dest / "melhores_valores.db").write_bytes(b"dados importantes")
        with pytest.raises(FileExistsError):
            copy_web_data.copy_to_sqlite(_raw(), dest)
        assert (dest / "melhores_valores.db").read_bytes() == b"dados importantes"


class TestFetchIsReadOnly:
    def test_connection_is_read_only_and_only_selects(self, monkeypatch):
        conn = MagicMock()
        executed = []
        conn.execute.side_effect = lambda sql: (executed.append((sql, conn.read_only)), MagicMock(fetchall=lambda: []))[1]
        psycopg = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = conn
        monkeypatch.setitem(sys.modules, "psycopg", psycopg)
        monkeypatch.setitem(sys.modules, "psycopg.rows", MagicMock())

        data = copy_web_data.fetch_web_data("postgresql://u:p@h/db?schema=public", with_search_results=True)

        assert set(data) == {"Product", "PriceHistory", "SearchResult"}
        assert all(sql.lstrip().upper().startswith("SELECT") for sql, _ in executed)
        assert all(read_only is True for _, read_only in executed)
        assert "schema=" not in psycopg.connect.call_args.args[0]

    def test_search_results_are_optional(self, monkeypatch):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        psycopg = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = conn
        monkeypatch.setitem(sys.modules, "psycopg", psycopg)
        monkeypatch.setitem(sys.modules, "psycopg.rows", MagicMock())

        assert set(copy_web_data.fetch_web_data("postgresql://x", with_search_results=False)) == {"Product", "PriceHistory"}


class TestMain:
    def test_dry_run_reads_but_writes_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(copy_web_data, "fetch_web_data", lambda url, with_sr: _raw())
        dest = tmp_path / "copia"
        assert copy_web_data.main(["--source", "postgresql://x", "--dest", str(dest), "--dry-run"]) == 0
        assert not dest.exists()
        assert "'Product': 1" in capsys.readouterr().out

    def test_existing_destination_aborts_before_reading_postgres(self, tmp_path, monkeypatch):
        fetch = MagicMock()
        monkeypatch.setattr(copy_web_data, "fetch_web_data", fetch)
        (tmp_path / "melhores_valores.db").write_bytes(b"x")
        assert copy_web_data.main(["--source", "postgresql://x", "--dest", str(tmp_path)]) == 1
        fetch.assert_not_called()

    def test_unreachable_postgres_is_reported(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(copy_web_data, "fetch_web_data", MagicMock(side_effect=OSError("connection refused")))
        assert copy_web_data.main(["--source", "postgresql://x", "--dest", str(tmp_path / "c")]) == 1
        assert "docker start price_tracker_db" in capsys.readouterr().err
