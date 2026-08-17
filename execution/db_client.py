import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from prisma import Prisma
from prisma.models import Product, PriceHistory

_BRT = ZoneInfo("America/Sao_Paulo")


def _is_same_brt_day(a: datetime, b: datetime) -> bool:
    return a.astimezone(_BRT).date() == b.astimezone(_BRT).date()

load_dotenv()

logger = logging.getLogger(__name__)

db = Prisma()

def connect_db():
    """
    Inicializa a conexão com o banco de dados PostgreSQL se necessário.
    Utilizado internamente pelas funções ou pode ser chamado explicitamente no startup da aplicação.
    """
    if not db.is_connected():
        logger.info("Estabelecendo conexão síncrona com o PostgreSQL...")
        
        # Bugfix: Celery substitui o sys.stdout por um LoggingProxy sem método fileno()
        # O Prisma-Python usa Popen por baixo dos panos e quebra requerendo esse método.
        if not hasattr(sys.stdout, 'fileno'):
            sys.stdout.fileno = lambda: 1
        if not hasattr(sys.stderr, 'fileno'):
            sys.stderr.fileno = lambda: 2
            
        db.connect()

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
    connect_db()
    try:
        product = db.product.find_unique(where={"url": url})

        if not product:
            logger.info(f"Novo produto detectado. Cadastrando URL: {url}")
            product = db.product.create(
                data={
                    "url": url,
                    "name": name,
                    "imageUrl": image_url,
                    "store": store or "unknown",
                }
            )
        elif name and not _is_garbage_name(name) and (
            _is_garbage_name(product.name) or product.name is None
        ):
            # Atualiza nome nulo ou com erro (ex: "Rate Limited") para um nome real
            logger.info(f"Atualizando nome '{product.name}' → '{name}' para {url}")
            product = db.product.update(
                where={"id": product.id},
                data={"name": name, "imageUrl": image_url or product.imageUrl},
            )

        return product
    except Exception as e:
        logger.error(f"Falha ao obter ou criar produto para url {url}: {e}")
        raise

def get_product_by_id(product_id: str) -> Product | None:
    """Retorna um produto pelo ID, ou None se não existir."""
    connect_db()
    try:
        return db.product.find_unique(where={"id": product_id})
    except Exception as e:
        logger.error(f"Erro ao buscar produto {product_id}: {e}")
        return None


def update_product_name(product_id: str, name: str) -> Product | None:
    """Atualiza manualmente o nome de um produto pelo ID."""
    connect_db()
    try:
        return db.product.update(where={"id": product_id}, data={"name": name})
    except Exception as e:
        logger.error(f"Erro ao atualizar nome do produto {product_id}: {e}")
        return None


def update_product_status(product_id: str, status: str) -> Product | None:
    """Atualiza o status de monitoramento de um produto ('active' ou 'paused')."""
    connect_db()
    try:
        return db.product.update(where={"id": product_id}, data={"status": status})
    except Exception as e:
        logger.error(f"Erro ao atualizar status do produto {product_id}: {e}")
        return None


def add_price_history(product_id: str, price: float | None, in_stock: bool = True) -> PriceHistory | None:
    """
    Registra uma nova entrada de preço para um produto específico, com deduplicação:
    só insere se price/inStock mudaram desde o último registro, ou se ainda não existe
    registro para o dia corrente (calendário de America/Sao_Paulo).

    Args:
        product_id (str): ID único (CUID) do produto.
        price (float, optional): Valor numérico do preço capturado. None se esgotado.
        in_stock (bool): Se o produto está disponível para compra.

    Returns:
        PriceHistory | None: O registro criado, ou None se a escrita foi deduplicada.
    """
    connect_db()
    try:
        last = db.pricehistory.find_first(
            where={"productId": product_id},
            order={"scrapedAt": "desc"},
        )
        if last is not None:
            changed = (last.price != price) or (last.inStock != in_stock)
            same_day = _is_same_brt_day(last.scrapedAt, datetime.now(timezone.utc))
            if not changed and same_day:
                logger.info(f"Dedup: preço inalterado para {product_id}, ignorando insert.")
                return None

        logger.info(f"Registrando preço {price} para produto_id: {product_id} (Estoque: {in_stock})")
        return db.pricehistory.create(
            data={
                "price": price,
                "inStock": in_stock,
                "productId": product_id
            }
        )
    except Exception as e:
        logger.error(f"Erro ao inserir histórico de preço para {product_id}: {e}")
        raise


def get_price_stats(product_id: str) -> dict:
    """
    Calcula estatísticas de preço agregadas no banco (não em Python).

    Returns:
        dict: current_price, lowest_price, average_price, median_price.
    """
    connect_db()
    try:
        latest = db.pricehistory.find_first(
            where={"productId": product_id},
            order={"scrapedAt": "desc"},
        )
        # prisma-client-py (v0.11) não expõe .aggregate() como método de conveniência,
        # então min/média/mediana são calculados numa única query raw no Postgres.
        rows = db.query_raw(
            '''SELECT
                   MIN(price) AS lowest,
                   AVG(price) AS average,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median
               FROM "PriceHistory"
               WHERE "productId" = $1 AND price IS NOT NULL''',
            product_id,
        )
        row = rows[0] if rows else {}

        return {
            "current_price": latest.price if latest else None,
            "lowest_price": float(row["lowest"]) if row.get("lowest") is not None else None,
            "average_price": round(float(row["average"]), 2) if row.get("average") is not None else None,
            "median_price": round(float(row["median"]), 2) if row.get("median") is not None else None,
        }
    except Exception as e:
        logger.error(f"Erro ao calcular estatísticas de preço para {product_id}: {e}")
        raise


def get_latest_price_entry(product_id: str) -> PriceHistory | None:
    """Retorna a linha de histórico mais recente do produto, ou None se não houver nenhuma."""
    connect_db()
    try:
        return db.pricehistory.find_first(
            where={"productId": product_id},
            order={"scrapedAt": "desc"},
        )
    except Exception as e:
        logger.error(f"Erro ao buscar entrada de preço mais recente para {product_id}: {e}")
        raise


def get_price_history_chart(product_id: str, days: int | None) -> list[PriceHistory]:
    """Retorna os pontos de histórico dentro da janela de dias informada (ou tudo, se None), mais antigos primeiro."""
    connect_db()
    try:
        where = {"productId": product_id}
        if days is not None:
            where["scrapedAt"] = {"gte": datetime.now(timezone.utc) - timedelta(days=days)}
        return db.pricehistory.find_many(where=where, order={"scrapedAt": "asc"})
    except Exception as e:
        logger.error(f"Erro ao buscar série de histórico para {product_id}: {e}")
        raise


def get_price_history_page(product_id: str, page: int, limit: int) -> tuple[list[PriceHistory], int]:
    """Retorna uma página do histórico bruto (mais recentes primeiro) e o total de registros."""
    connect_db()
    try:
        total = db.pricehistory.count(where={"productId": product_id})
        entries = db.pricehistory.find_many(
            where={"productId": product_id},
            order={"scrapedAt": "desc"},
            skip=(page - 1) * limit,
            take=limit,
        )
        return entries, total
    except Exception as e:
        logger.error(f"Erro ao buscar página de histórico para {product_id}: {e}")
        raise


def get_all_products() -> list:
    """Retorna todos os produtos com a última entrada de preço (para exibição no dashboard)."""
    connect_db()
    try:
        return db.product.find_many(
            order={"createdAt": "desc"},
            include={
                "history": {
                    "order_by": {"scrapedAt": "desc"},
                    "take": 1,
                },
            },
        )
    except Exception as e:
        logger.error(f"Erro ao buscar produtos: {e}")
        raise


def get_products_with_history() -> list:
    """Retorna todos os produtos com o histórico de preços completo (mais recentes primeiro)."""
    connect_db()
    try:
        return db.product.find_many(
            order={"createdAt": "desc"},
            include={
                "history": {
                    "order_by": {"scrapedAt": "desc"},
                },
            },
        )
    except Exception as e:
        logger.error(f"Erro ao buscar produtos com histórico: {e}")
        raise


def delete_product(product_id: str) -> bool:
    """
    Remove um produto e todo seu histórico de preços pelo ID.
    O histórico é deletado em cascata pelo banco.

    Returns:
        True se deletado, False se não encontrado.
    """
    connect_db()
    try:
        db.pricehistory.delete_many(where={"productId": product_id})
        deleted = db.product.delete(where={"id": product_id})
        logger.info(f"Produto {product_id} removido com sucesso.")
        return deleted is not None
    except Exception as e:
        logger.error(f"Erro ao deletar produto {product_id}: {e}")
        return False


# ─────────────────────────────────────────────
# SearchResult — Busca automática de produtos
# ─────────────────────────────────────────────

def save_search_results(search_id: str, query: str, results: list[dict]) -> int:
    """
    Persiste a lista de resultados de busca no banco de dados.
    Segue o padrão síncrono do projeto (prisma-client-python).

    Args:
        search_id: UUID que agrupa todos os resultados desta busca.
        query: Termo buscado pelo usuário (ex: "iPhone 15").
        results: Lista de dicts normalizados retornados pelos search_scrapers.

    Returns:
        Número de registros salvos com sucesso.
    """
    connect_db()
    saved = 0
    for item in results:
        try:
            db.searchresult.create(data={
                "search_id":    search_id,
                "query":        query,
                "store":        item["store"],
                "title":        item["title"],
                "price":        item.get("price"),
                "currency":     item.get("currency", "BRL"),
                "image_url":    item.get("image_url"),
                "product_url":  item["product_url"],
                "rating":       item.get("rating"),
                "review_count": item.get("review_count"),
            })
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
    connect_db()
    try:
        product = db.product.find_unique(where={"url": url})
        if not product:
            return None
        entries = db.pricehistory.find_many(
            where={"productId": product.id, "inStock": True},
            order={"scrapedAt": "desc"},
            take=1,
        )
        if entries and entries[0].price and entries[0].price > 0:
            return entries[0].price
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
    connect_db()
    try:
        return db.searchresult.find_many(
            where={"search_id": search_id},
            order={"price": "asc"},
        )
    except Exception as e:
        logger.error(f"[db_client] Erro ao buscar SearchResults: {e}")
        return []
