import uuid

from execution.search_scrapers.amazon_search       import search_amazon
from execution.search_scrapers.mercadolivre_search import search_mercadolivre
from execution.search_scrapers.shopee_search       import search_shopee
from execution.db_client                           import save_search_results

SEARCH_FUNCTIONS = [
    search_amazon,
    search_mercadolivre,
    # search_shopee,  # Ignorado por enquanto a pedido do usuário
]

def run_product_search(query: str) -> str:
    """
    Executa a busca por nome do produto nas 3 lojas e persiste os resultados.

    Fluxo:
        1. Gera um search_id único para agrupar os resultados desta busca
        2. Chama cada scraper de busca (Amazon, Mercado Livre, Shopee)
        3. Agrega todos os resultados normalizados
        4. Delega a persistência ao db_client (única interface com o banco)
        5. Retorna o search_id para o cliente consultar via GET /search/{id}

    Args:
        query: Termo de busca informado pelo usuário (ex: "iPhone 15 128GB").

    Returns:
        search_id (UUID string) para consulta posterior dos resultados.
    """
    search_id   = str(uuid.uuid4())
    all_results = []

    for search_fn in SEARCH_FUNCTIONS:
        try:
            results = search_fn(query, max_results=10)
            all_results.extend(results)
            print(f"[search_orchestrator] {search_fn.__name__}: {len(results)} resultados")
        except Exception as e:
            print(f"[search_orchestrator] {search_fn.__name__} falhou: {e}")
            continue

    saved = save_search_results(search_id, query, all_results)
    print(f"[search_orchestrator] {saved}/{len(all_results)} resultados salvos | query='{query}' | id={search_id}")

    return search_id
