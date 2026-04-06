import logging
from typing import Optional
from dotenv import load_dotenv
from prisma import Prisma
from prisma.models import Product, PriceHistory

# Carrega variáveis de ambiente (.env) para o Prisma localizar o DATABASE_URL
load_dotenv()

# Configuração de logging para a camada de execução
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instância global do cliente Prisma.
# Como o gerador foi configurado com interface = "sync", as chamadas serão bloqueantes (síncronas).
db = Prisma()

import sys

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
                    "store": store or "unknown"
                }
            )
        return product
    except Exception as e:
        logger.error(f"Falha ao obter ou criar produto para url {url}: {e}")
        raise

def add_price_history(product_id: str, price: Optional[float], in_stock: bool = True) -> PriceHistory:
    """
    Registra uma nova entrada de preço para um produto específico.

    Args:
        product_id (str): ID único (CUID) do produto.
        price (float, optional): Valor numérico do preço capturado. None se esgotado.
        in_stock (bool): Se o produto está disponível para compra.

    Returns:
        PriceHistory: O registro do histórico de preço criado.
    """
    connect_db()
    try:
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

def get_product_with_history(product_id: str) -> dict:
    """
    Recupera os detalhes de um produto e toda sua árvore de preços vinculada.
    Os preços são ordenados de forma decrescente por data (mais recentes primeiro).

    Args:
        product_id (str): ID do produto para busca.

    Returns:
        dict: Dicionário completo do produto incluindo a lista 'history', ou dicionário vazio se não encontrado.
    """
    connect_db()
    try:
        product = db.product.find_unique(
            where={"id": product_id},
            include={
                "history": {
                    "order_by": {
                        "scrapedAt": "desc"
                    }
                }
            }
        )
        
        if not product:
            logger.warning(f"Produto não encontrado no banco para o ID: {product_id}")
            return {}
            
        # Converte o modelo Prisma/Pydantic em um dicionário Python para fácil consumo no front-end
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
