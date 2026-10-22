import logging
import sqlite3
import statistics
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from .db_schema import MIGRATIONS
from .models import PriceHistory, Product, SearchResult
from .settings import DB_PATH

_BRT = ZoneInfo("America/Sao_Paulo")


def _is_same_brt_day(a: datetime, b: datetime) -> bool:
    return a.astimezone(_BRT).date() == b.astimezone(_BRT).date()


def _iso(dt: datetime) -> str:
    """Formato único de data no banco: ISO 8601 em UTC com microssegundos.
    Mantém a ordenação e as comparações por texto (ORDER BY / >=) corretas."""
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


logger = logging.getLogger(__name__)

# Uma conexão por thread (API + workers rodam em threads diferentes). O SQLite
# em modo WAL permite leituras concorrentes; as escritas são serializadas pelo
# lock para que leitura-seguida-de-escrita (get_or_create, dedup) seja atômica.
_local = threading.local()
_write_lock = threading.RLock()


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        logger.info("Aplicando migração do banco: v%d → v%d", target - 1, target)
        try:
            conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {target};\nCOMMIT;")
        except Exception:
            conn.rollback()
            raise


def connect_db() -> sqlite3.Connection:
    """
    Retorna a conexão SQLite da thread atual, abrindo-a (e aplicando as
    migrações pendentes) se necessário.
    Utilizado internamente pelas funções ou pode ser chamado explicitamente no startup da aplicação.
    """
    path = Path(DB_PATH)
    cached = getattr(_local, "conn", None)
    if cached is not None:
        if cached[0] == path:
            return cached[1]
        cached[1].close()

    logger.info("Abrindo banco SQLite em %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Trocar o journal_mode e migrar exigem o banco só para si: duas threads
    # abrindo a primeira conexão ao mesmo tempo dariam "database is locked".
    with _write_lock:
        conn.execute("PRAGMA journal_mode = WAL")
        _migrate(conn)
    _local.conn = (path, conn)
    return conn


def close_db() -> None:
    """Fecha a conexão da thread atual (usado no shutdown e nos testes)."""
    cached = getattr(_local, "conn", None)
    if cached is not None:
        cached[1].close()
        _local.conn = None


@contextmanager
def _write() -> Iterator[sqlite3.Connection]:
    """Transação de escrita: commit ao sair, rollback em exceção."""
    conn = connect_db()
    with _write_lock, conn:
        yield conn


def _product(row: sqlite3.Row, history: list[PriceHistory] | None = None) -> Product:
    return Product(**dict(row), history=history)


def _history(row: sqlite3.Row) -> PriceHistory:
    return PriceHistory(**dict(row))


# Fragmentos que indicam erro de scraping (rate limit, bloqueio anti-bot, etc.)
# Verificação por substring — qualquer nome que CONTENHA um desses fragmentos é descartado.
_GARBAGE_FRAGMENTS = {
    # Inglês
    "rate limited", "access denied", "forbidden", "captcha",
    "just a moment", "bot detected", "503 service", "429 too many",
    "blocked", "unavailable", "cloudflare",
    # Português
    "acesso negado", "acesso bloqueado", "atenção", "você foi bloqueado",
    "não é possível", "página não encontrada", "erro ao carregar",
    "verificação de segurança", "robô", "bot detectado",
}


def _is_garbage_name(name: str | None) -> bool:
    """Retorna True se o nome parece ser um erro de scraping."""
    if not name or len(name.strip()) < 3:
        return True
    lower = name.strip().lower()
    return any(fragment in lower for fragment in _GARBAGE_FRAGMENTS)


# Public alias — import this in other modules instead of duplicating the logic
is_garbage_name = _is_garbage_name


def get_or_create_product(url: str, name: str | None = None, store: str | None = None, image_url: str | None = None) -> Product:
    """
    Busca um produto na tabela Product pela URL (única).
    Se não existir, cria. Se existir com nome inválido (rate limit, erro), atualiza.

    Args:
        url (str): Link direto do produto no e-commerce.
        name (str, optional): Nome legível do produto.
        store (str, optional): Identificador da loja (amazon, mercadolivre, etc).
        image_url (str, optional): URL da imagem do produto.

    Returns:
        Product: O objeto do produto (existente ou recém-criado).
    """
    try:
        with _write() as conn:
            row = conn.execute("SELECT * FROM Product WHERE url = ?", (url,)).fetchone()

            if not row:
                logger.info(f"Novo produto detectado. Cadastrando URL: {url}")
                now = _now_iso()
                product_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO Product (id, url, name, imageUrl, store, createdAt, updatedAt)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (product_id, url, name, image_url, store or "unknown", now, now),
                )
            elif name and not _is_garbage_name(name) and (
                _is_garbage_name(row["name"]) or row["name"] is None
            ):
                # Atualiza nome nulo ou com erro (ex: "Rate Limited") para um nome real
                logger.info(f"Atualizando nome '{row['name']}' → '{name}' para {url}")
                product_id = row["id"]
                conn.execute(
                    "UPDATE Product SET name = ?, imageUrl = ?, updatedAt = ? WHERE id = ?",
                    (name, image_url or row["imageUrl"], _now_iso(), product_id),
                )
            else:
                return _product(row)

            return _product(conn.execute("SELECT * FROM Product WHERE id = ?", (product_id,)).fetchone())
    except Exception as e:
        logger.error(f"Falha ao obter ou criar produto para url {url}: {e}")
        raise

def get_product_by_id(product_id: str) -> Product | None:
    """Retorna um produto pelo ID, ou None se não existir."""
    try:
        row = connect_db().execute("SELECT * FROM Product WHERE id = ?", (product_id,)).fetchone()
        return _product(row) if row else None
    except Exception as e:
        logger.error(f"Erro ao buscar produto {product_id}: {e}")
        return None


def _update_product(product_id: str, field: str, value: str) -> Product | None:
    with _write() as conn:
        cursor = conn.execute(
            f"UPDATE Product SET {field} = ?, updatedAt = ? WHERE id = ?",
            (value, _now_iso(), product_id),
        )
        if cursor.rowcount == 0:
            return None
        return _product(conn.execute("SELECT * FROM Product WHERE id = ?", (product_id,)).fetchone())


def update_product_name(product_id: str, name: str) -> Product | None:
    """Atualiza manualmente o nome de um produto pelo ID."""
    try:
        return _update_product(product_id, "name", name)
    except Exception as e:
        logger.error(f"Erro ao atualizar nome do produto {product_id}: {e}")
        return None


def update_product_status(product_id: str, status: str) -> Product | None:
    """Atualiza o status de monitoramento de um produto ('active' ou 'paused')."""
    try:
        return _update_product(product_id, "status", status)
    except Exception as e:
        logger.error(f"Erro ao atualizar status do produto {product_id}: {e}")
        return None


def add_price_history(product_id: str, price: float | None, in_stock: bool = True) -> PriceHistory | None:
    """
    Registra uma nova entrada de preço para um produto específico, com deduplicação:
    só insere se price/inStock mudaram desde o último registro, ou se ainda não existe
    registro para o dia corrente (calendário de America/Sao_Paulo).

    Args:
        product_id (str): ID único (UUID) do produto.
        price (float, optional): Valor numérico do preço capturado. None se esgotado.
        in_stock (bool): Se o produto está disponível para compra.

    Returns:
        PriceHistory | None: O registro criado, ou None se a escrita foi deduplicada.
    """
    try:
        with _write() as conn:
            row = conn.execute(
                "SELECT * FROM PriceHistory WHERE productId = ? ORDER BY scrapedAt DESC LIMIT 1",
                (product_id,),
            ).fetchone()
            if row is not None:
                last = _history(row)
                changed = (last.price != price) or (last.inStock != in_stock)
                same_day = _is_same_brt_day(last.scrapedAt, datetime.now(timezone.utc))
                if not changed and same_day:
                    logger.info(f"Dedup: preço inalterado para {product_id}, ignorando insert.")
                    return None

            logger.info(f"Registrando preço {price} para produto_id: {product_id} (Estoque: {in_stock})")
            entry = PriceHistory(
                id=str(uuid.uuid4()),
                price=price,
                inStock=in_stock,
                scrapedAt=datetime.now(timezone.utc),
                productId=product_id,
            )
            conn.execute(
                "INSERT INTO PriceHistory (id, price, inStock, scrapedAt, productId) VALUES (?, ?, ?, ?, ?)",
                (entry.id, entry.price, entry.inStock, _iso(entry.scrapedAt), entry.productId),
            )
            return entry
    except Exception as e:
        logger.error(f"Erro ao inserir histórico de preço para {product_id}: {e}")
        raise


def _price_summary(prices: list[float]) -> tuple[float | None, float | None, float | None]:
    """(menor, média, mediana) de uma lista de preços; mediana igual ao
    percentile_cont(0.5) do Postgres (média dos dois centrais em lista par)."""
    if not prices:
        return None, None, None
    return (
        float(min(prices)),
        round(statistics.fmean(prices), 2),
        round(float(statistics.median(prices)), 2),
    )


def get_price_stats(product_id: str) -> dict:
    """
    Calcula estatísticas de preço sobre todo o histórico do produto.

    Returns:
        dict: current_price, lowest_price, average_price, median_price.
    """
    try:
        conn = connect_db()
        latest = get_latest_price_entry(product_id)
        prices = [
            r["price"] for r in conn.execute(
                "SELECT price FROM PriceHistory WHERE productId = ? AND price IS NOT NULL",
                (product_id,),
            )
        ]
        lowest, average, median = _price_summary(prices)

        return {
            "current_price": latest.price if latest else None,
            "lowest_price": lowest,
            "average_price": average,
            "median_price": median,
        }
    except Exception as e:
        logger.error(f"Erro ao calcular estatísticas de preço para {product_id}: {e}")
        raise


def get_group_price_stats(product_ids: list[str]) -> dict:
    """
    Calcula estatísticas agregadas (mínimo e mediana reais, sobre os preços
    pooled de várias listagens) — usado pelo card de grupo no modal, para não
    depender de combinar estatísticas por listagem no cliente (mediana não é
    distributiva: mediana das medianas != mediana do conjunto completo).

    Returns:
        dict: lowest_price, median_price.
    """
    if not product_ids:
        return {"lowest_price": None, "median_price": None}
    try:
        placeholders = ", ".join("?" for _ in product_ids)
        prices = [
            r["price"] for r in connect_db().execute(
                f"SELECT price FROM PriceHistory WHERE productId IN ({placeholders}) AND price IS NOT NULL",
                product_ids,
            )
        ]
        lowest, _, median = _price_summary(prices)

        return {"lowest_price": lowest, "median_price": median}
    except Exception as e:
        logger.error(f"Erro ao calcular estatísticas de grupo para {product_ids}: {e}")
        raise


def get_latest_price_entry(product_id: str) -> PriceHistory | None:
    """Retorna a linha de histórico mais recente do produto, ou None se não houver nenhuma."""
    try:
        row = connect_db().execute(
            "SELECT * FROM PriceHistory WHERE productId = ? ORDER BY scrapedAt DESC LIMIT 1",
            (product_id,),
        ).fetchone()
        return _history(row) if row else None
    except Exception as e:
        logger.error(f"Erro ao buscar entrada de preço mais recente para {product_id}: {e}")
        raise


def get_price_history_chart(product_id: str, days: int | None) -> list[PriceHistory]:
    """Retorna os pontos de histórico dentro da janela de dias informada (ou tudo, se None), mais antigos primeiro."""
    try:
        sql = "SELECT * FROM PriceHistory WHERE productId = ?"
        params: list = [product_id]
        if days is not None:
            sql += " AND scrapedAt >= ?"
            params.append(_iso(datetime.now(timezone.utc) - timedelta(days=days)))
        rows = connect_db().execute(sql + " ORDER BY scrapedAt ASC", params).fetchall()
        return [_history(r) for r in rows]
    except Exception as e:
        logger.error(f"Erro ao buscar série de histórico para {product_id}: {e}")
        raise


def get_price_history_page(product_id: str, page: int, limit: int) -> tuple[list[PriceHistory], int]:
    """Retorna uma página do histórico bruto (mais recentes primeiro) e o total de registros."""
    try:
        conn = connect_db()
        total = conn.execute(
            "SELECT COUNT(*) FROM PriceHistory WHERE productId = ?", (product_id,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM PriceHistory WHERE productId = ? ORDER BY scrapedAt DESC LIMIT ? OFFSET ?",
            (product_id, limit, (page - 1) * limit),
        ).fetchall()
        return [_history(r) for r in rows], total
    except Exception as e:
        logger.error(f"Erro ao buscar página de histórico para {product_id}: {e}")
        raise


def _products_with_history(latest_only: bool) -> list[Product]:
    conn = connect_db()
    if latest_only:
        history_sql = """
            SELECT id, price, inStock, scrapedAt, productId FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY productId ORDER BY scrapedAt DESC) AS rn
                FROM PriceHistory
            ) WHERE rn = 1"""
    else:
        history_sql = "SELECT * FROM PriceHistory ORDER BY scrapedAt DESC"

    history_by_product: dict[str, list[PriceHistory]] = {}
    for row in conn.execute(history_sql):
        history_by_product.setdefault(row["productId"], []).append(_history(row))

    return [
        _product(row, history_by_product.get(row["id"], []))
        for row in conn.execute("SELECT * FROM Product ORDER BY createdAt DESC")
    ]


def get_all_products() -> list:
    """Retorna todos os produtos com a última entrada de preço (para exibição no dashboard)."""
    try:
        return _products_with_history(latest_only=True)
    except Exception as e:
        logger.error(f"Erro ao buscar produtos: {e}")
        raise


def get_products_with_history() -> list:
    """Retorna todos os produtos com o histórico de preços completo (mais recentes primeiro)."""
    try:
        return _products_with_history(latest_only=False)
    except Exception as e:
        logger.error(f"Erro ao buscar produtos com histórico: {e}")
        raise


def delete_product(product_id: str) -> bool:
    """
    Remove um produto e todo seu histórico de preços pelo ID.
    O histórico é deletado em cascata pelo banco (ON DELETE CASCADE).

    Returns:
        True se deletado, False se não encontrado.
    """
    try:
        with _write() as conn:
            cursor = conn.execute("DELETE FROM Product WHERE id = ?", (product_id,))
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Produto {product_id} removido com sucesso.")
        return deleted
    except Exception as e:
        logger.error(f"Erro ao deletar produto {product_id}: {e}")
        return False


# ─────────────────────────────────────────────
# SearchResult — Busca automática de produtos
# ─────────────────────────────────────────────

def save_search_results(search_id: str, query: str, results: list[dict]) -> int:
    """
    Persiste a lista de resultados de busca no banco de dados.

    Args:
        search_id: UUID que agrupa todos os resultados desta busca.
        query: Termo buscado pelo usuário (ex: "iPhone 15").
        results: Lista de dicts normalizados retornados pelos search_scrapers.

    Returns:
        Número de registros salvos com sucesso.
    """
    saved = 0
    found_at = _now_iso()
    with _write() as conn:
        for item in results:
            try:
                conn.execute(
                    """INSERT INTO SearchResult
                       (id, search_id, query, store, title, price, currency,
                        image_url, product_url, rating, review_count, found_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        search_id,
                        query,
                        item["store"],
                        item["title"],
                        item.get("price"),
                        item.get("currency", "BRL"),
                        item.get("image_url"),
                        item["product_url"],
                        item.get("rating"),
                        item.get("review_count"),
                        found_at,
                    ),
                )
                saved += 1
            except Exception as e:
                logger.error(f"[db_client] Erro ao salvar SearchResult: {e}")
                continue
    return saved


def get_last_valid_price_for_url(url: str) -> float | None:
    """
    Returns the most recent positive price recorded for a product URL.
    Used by worker_tasks for sanity-checking new scraped prices.
    Returns None if the product is new or has no price history.
    """
    try:
        row = connect_db().execute(
            """SELECT h.price FROM PriceHistory h
               JOIN Product p ON p.id = h.productId
               WHERE p.url = ? AND h.inStock = 1
               ORDER BY h.scrapedAt DESC LIMIT 1""",
            (url,),
        ).fetchone()
        if row and row["price"] and row["price"] > 0:
            return row["price"]
        return None
    except Exception as e:
        logger.error("Erro ao buscar último preço para sanity check | url=%s | %s", url, e)
        return None


def get_search_results(search_id: str) -> list:
    """
    Retorna todos os resultados de uma busca ordenados pelo menor preço.

    Args:
        search_id: UUID da busca a ser consultada.

    Returns:
        Lista de SearchResult ordenada por preço ascendente.
        Resultados sem preço (None) aparecem ao final.
    """
    try:
        rows = connect_db().execute(
            # SQLite ordena NULL primeiro; "price IS NULL" joga os sem preço para o fim
            "SELECT * FROM SearchResult WHERE search_id = ? ORDER BY price IS NULL, price ASC",
            (search_id,),
        ).fetchall()
        return [SearchResult(**dict(r)) for r in rows]
    except Exception as e:
        logger.error(f"[db_client] Erro ao buscar SearchResults: {e}")
        return []
