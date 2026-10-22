"""
Copia os dados da versão web (PostgreSQL) para um SQLite NOVO do app desktop.

Ferramenta de desenvolvimento, para testar o app com dados reais. Não entra no
executável (quem recebe o .exe começa com o banco vazio).

Garantias:
- O Postgres é aberto em modo SOMENTE LEITURA (transação READ ONLY): o script
  só faz SELECT e não tem como alterar os dados da versão web.
- O destino precisa ser um banco novo: se o arquivo já existir, nada é feito.
- A gravação no SQLite é uma transação única (tudo ou nada), via db_client.

Uso (com o Postgres da versão web rodando, ex: `docker start price_tracker_db`):
    pip install -r requirements-dev.txt
    python scripts/copy_web_data.py                          # → .data/copia-web/
    python scripts/copy_web_data.py --dest D:/outra/pasta --with-search-results
    python scripts/copy_web_data.py --dry-run                # só conta, não grava

Depois, para abrir o app com a cópia:
    $env:MV_DATA_DIR = ".data/copia-web"; python main.py     (PowerShell)
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DEST = REPO_ROOT / ".data" / "copia-web"
DB_FILENAME = "melhores_valores.db"

# Colunas iguais às do schema.prisma da versão web (e de execution/models.py)
_QUERIES = {
    "Product": 'SELECT id, url, name, "imageUrl", store, status, "createdAt", "updatedAt" '
               'FROM "Product" ORDER BY "createdAt"',
    "PriceHistory": 'SELECT id, price, "inStock", "scrapedAt", "productId" '
                    'FROM "PriceHistory" ORDER BY "scrapedAt"',
    "SearchResult": "SELECT id, search_id, query, store, title, price, currency, image_url, "
                    'product_url, rating, review_count, found_at FROM "SearchResult" ORDER BY found_at',
}


def default_source_url() -> str | None:
    """DATABASE_URL do .env do repositório (configuração da versão web)."""
    from dotenv import dotenv_values

    return dotenv_values(REPO_ROOT / ".env").get("DATABASE_URL")


def to_libpq_url(url: str) -> str:
    """Remove parâmetros que só o Prisma entende (ex: ?schema=public)."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("schema", "connection_limit", "pool_timeout")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def fetch_web_data(source_url: str, with_search_results: bool) -> dict[str, list[dict]]:
    """Lê as tabelas do Postgres numa transação READ ONLY."""
    import psycopg
    from psycopg.rows import dict_row

    tables = ["Product", "PriceHistory"] + (["SearchResult"] if with_search_results else [])
    with psycopg.connect(to_libpq_url(source_url), row_factory=dict_row, connect_timeout=5) as conn:
        conn.read_only = True  # qualquer INSERT/UPDATE/DELETE falharia no servidor
        with conn.transaction():
            return {table: conn.execute(_QUERIES[table]).fetchall() for table in tables}


def _as_utc(row: dict) -> dict:
    """O Prisma grava timestamp sem fuso, em UTC; o psycopg devolve datetime "ingênuo".
    Sem marcar como UTC, a conversão para ISO assumiria o fuso local (-3h no Brasil)."""
    return {
        k: v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) and v.tzinfo is None else v
        for k, v in row.items()
    }


def to_models(raw: dict[str, list[dict]]):
    from execution.models import PriceHistory, Product, SearchResult

    products = [Product(**_as_utc(r)) for r in raw.get("Product", [])]
    history = [PriceHistory(**_as_utc(r)) for r in raw.get("PriceHistory", [])]
    search_results = [SearchResult(**_as_utc(r)) for r in raw.get("SearchResult", [])]
    return products, history, search_results


def copy_to_sqlite(raw: dict[str, list[dict]], dest_dir: Path) -> dict[str, int]:
    from execution import db_client

    db_path = dest_dir / DB_FILENAME
    if db_path.exists():
        raise FileExistsError(f"{db_path} já existe — escolha outra pasta ou apague o arquivo antes.")

    products, history, search_results = to_models(raw)
    db_client.close_db()
    db_client.DB_PATH = db_path
    try:
        return db_client.bulk_import(products, history, search_results)
    finally:
        db_client.close_db()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", help="URL do Postgres da versão web (padrão: DATABASE_URL do .env)")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"pasta do SQLite novo (padrão: {DEFAULT_DEST})")
    parser.add_argument("--with-search-results", action="store_true", help="copiar também o histórico de buscas")
    parser.add_argument("--dry-run", action="store_true", help="só ler e contar, sem gravar nada")
    args = parser.parse_args(argv)

    source = args.source or default_source_url()
    if not source:
        print("Informe --source ou defina DATABASE_URL no .env.", file=sys.stderr)
        return 2

    dest_db = args.dest / DB_FILENAME
    if not args.dry_run and dest_db.exists():
        print(f"{dest_db} já existe — nada foi feito. Escolha outra --dest ou apague o arquivo.", file=sys.stderr)
        return 1

    try:
        raw = fetch_web_data(source, args.with_search_results)
    except Exception as e:
        print(f"Não foi possível ler o Postgres da versão web: {e}", file=sys.stderr)
        print("Ele está rodando? (ex: docker start price_tracker_db)", file=sys.stderr)
        return 1

    counts = {table: len(rows) for table, rows in raw.items()}
    print("Lido da versão web (somente leitura):", counts)
    if args.dry_run:
        return 0

    result = copy_to_sqlite(raw, args.dest)
    print("Gravado em", dest_db, "→", result)
    print(f'Para abrir o app com a cópia (PowerShell): $env:MV_DATA_DIR = "{args.dest}"; python main.py')
    return 0


if __name__ == "__main__":
    sys.exit(main())
