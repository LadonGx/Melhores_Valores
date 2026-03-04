import logging
import sys
from typing import Optional

from dotenv import load_dotenv
from prisma import Prisma
from prisma.models import PriceHistory, Product

# Carrega variáveis de ambiente (.env) para o Prisma localizar o DATABASE_URL
load_dotenv()

# Configuração de logging para a camada de execução
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instância global do cliente Prisma.
# Como o gerador foi configurado com interface = "sync", as chamadas serão bloqueantes (síncronas).
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
        if not hasattr(sys.stdout, "fileno"):
            sys.stdout.fileno = lambda: 1
        if not hasattr(sys.stderr, "fileno"):
            sys.stderr.fileno = lambda: 2

        db.connect()


def disconnect_db():
    """
    Encerra a conexão com o banco de dados.
    Deve ser chamado no shutdown do servidor ou worker para liberar recursos.
    """
    if db.is_connected():
        logger.info("Encerrando conexão com o PostgreSQL...")
        db.disconnect()


def get_or_create_product(url: str, name: str = None, store: str = None, image_url: str = None) -> Product:
    """
    Busca um produto na tabela Product pela URL (única).
    Se o produto não existir, realiza a criação com os dados fornecidos.
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
        return product
    except Exception as e:
        logger.error(f"Falha ao obter ou criar produto para url {url}: {e}")
        raise


def add_price_history(product_id: str, price: Optional[float], in_stock: bool = True) -> PriceHistory:
    """Registra uma nova entrada de preço para um produto específico."""
    connect_db()
    try:
        logger.info(f"Registrando preço {price} para produto_id: {product_id} (Estoque: {in_stock})")
        return db.pricehistory.create(data={"price": price, "inStock": in_stock, "productId": product_id})
    except Exception as e:
        logger.error(f"Erro ao inserir histórico de preço para {product_id}: {e}")
        raise


def save_automatic_search_results(query: str, store: str, products: list[dict]) -> int:
    """Persiste os produtos encontrados na busca automática em uma tabela dedicada."""
    connect_db()

    inserted = 0
    for index, product in enumerate(products, start=1):
        try:
            db.automaticsearchresult.create(
                data={
                    "query": query,
                    "store": store,
                    "productUrl": product.get("url"),
                    "productName": product.get("name"),
                    "price": product.get("price"),
                    "imageUrl": product.get("image_url"),
                    "position": product.get("position") or index,
                }
            )
            inserted += 1
        except Exception as exc:
            logger.error(
                "Erro ao salvar resultado automático. query=%s store=%s url=%s erro=%s",
                query,
                store,
                product.get("url"),
                exc,
            )

    return inserted


def get_product_with_history(product_id: str) -> dict:
    """
    Recupera os detalhes de um produto e toda sua árvore de preços vinculada.
    Os preços são ordenados de forma decrescente por data (mais recentes primeiro).
    """
    connect_db()
    try:
        product = db.product.find_unique(
            where={"id": product_id},
            include={"history": {"order_by": {"scrapedAt": "desc"}}},
        )

        if not product:
            logger.warning(f"Produto não encontrado no banco para o ID: {product_id}")
            return {}

        return product.model_dump()
    except Exception as e:
        logger.error(f"Erro ao buscar produto com histórico para {product_id}: {e}")
        raise


def get_all_products() -> list[Product]:
    """Retorna todos os produtos cadastrados para agendamento em lote."""
    connect_db()
    try:
        return db.product.find_many()
    except Exception as e:
        logger.error(f"Erro ao buscar produtos para agendamento: {e}")
        raise
