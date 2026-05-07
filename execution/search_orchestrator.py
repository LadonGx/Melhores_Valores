import re
import uuid

from execution.search_scrapers.amazon_search       import search_amazon
from execution.search_scrapers.mercadolivre_search import search_mercadolivre
from execution.db_client                           import save_search_results

# Magazine Luiza (shopee_search.py) está temporariamente desativado:
# o site bloqueia IPs de datacenter independente de User-Agent ou Playwright.
# Para reativar, seria necessário proxies residenciais.
SEARCH_FUNCTIONS = [
    search_amazon,
    search_mercadolivre,
]

# Palavras comuns em PT-BR descartadas na comparação de relevância
_STOPWORDS = {
    "a", "as", "o", "os", "e", "é", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "um", "uma", "uns", "umas",
    "com", "por", "para", "que", "se", "ou", "ao", "aos", "at",
    "vol", "volume", "the", "of", "in", "ed", "edicao", "edicão",
}

# Pontuação relevante mínima: 50% dos tokens da query devem aparecer no título
RELEVANCE_THRESHOLD = 0.5


def _tokenize(text: str) -> set[str]:
    """Extrai tokens relevantes ignorando stopwords e tokens com 1 caractere."""
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


def _is_relevant(query: str, title: str) -> bool:
    """
    Retorna True se o título tem sobreposição suficiente com a query.

    Para queries com 1 token: exige correspondência exata desse token.
    Para queries com 2+ tokens: exige >= RELEVANCE_THRESHOLD de sobreposição.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return True

    title_tokens = _tokenize(title)
    overlap = query_tokens & title_tokens
    score = len(overlap) / len(query_tokens)

    return score >= RELEVANCE_THRESHOLD


def _filter_relevant(query: str, results: list[dict]) -> list[dict]:
    """Remove resultados cujo título não tem relação suficiente com a query."""
    filtered = [r for r in results if _is_relevant(query, r.get("title", ""))]
    removed = len(results) - len(filtered)
    if removed:
        print(f"[search_orchestrator] {removed} resultado(s) descartados por baixa relevância")
    return filtered


def run_product_search(query: str, search_id: str | None = None) -> str:
    """
    Executa a busca por nome do produto nas lojas e persiste os resultados.

    Args:
        query: Termo de busca informado pelo usuário (ex: "iPhone 15 128GB").
        search_id: ID externo a usar (ex: task.id do Celery). Se None, gera um UUID.
                   Deve ser o mesmo ID retornado ao cliente para que o polling funcione.

    Returns:
        search_id usado para persistência — consultar via GET /search/{search_id}.
    """
    if not search_id:
        search_id = str(uuid.uuid4())

    all_results = []

    for search_fn in SEARCH_FUNCTIONS:
        try:
            results = search_fn(query, max_results=10)
            print(f"[search_orchestrator] {search_fn.__name__}: {len(results)} resultados brutos")
            all_results.extend(results)
        except Exception as e:
            print(f"[search_orchestrator] {search_fn.__name__} falhou: {e}")
            continue

    # Filtra resultados irrelevantes antes de persistir
    relevant_results = _filter_relevant(query, all_results)

    saved = save_search_results(search_id, query, relevant_results)
    print(
        f"[search_orchestrator] {saved}/{len(relevant_results)} relevantes salvos "
        f"(de {len(all_results)} brutos) | query='{query}' | id={search_id}"
    )

    return search_id
