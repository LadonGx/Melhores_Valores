import logging
import re
import uuid

from .search_scrapers.amazon_search       import search_amazon
from .search_scrapers.mercadolivre_search import search_mercadolivre
from .db_client                           import save_search_results

logger = logging.getLogger(__name__)

# Magazine Luiza and Shopee are disabled: blocked from datacenter IPs regardless
# of User-Agent or Playwright. Re-enable only with residential proxies.
SEARCH_FUNCTIONS = [
    search_amazon,
    search_mercadolivre,
]

# PT-BR stopwords to ignore during relevance scoring
_STOPWORDS = {
    "a", "as", "o", "os", "e", "é", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "um", "uma", "uns", "umas",
    "com", "por", "para", "que", "se", "ou", "ao", "aos", "at",
    "vol", "volume", "the", "of", "in", "ed", "edicao", "edição",
}

# Ad/noise terms that should be stripped from titles before scoring
_NOISE_TERMS = (
    "patrocinado", "sponsored", "novo anúncio", "novo anuncio",
    "melhor preço", "frete grátis", "entrega grátis",
)

# Tokens matching these patterns are specification tokens (model/capacity/voltage).
# They receive double weight because mismatching a spec (e.g., 128GB vs 512GB) is critical.
_SPEC_PATTERN = re.compile(r"^\d+(?:gb|tb|mb|hz|kg|ml|v|w)?$")

# Minimum weighted relevance ratio to include a result
_RELEVANCE_THRESHOLD = 0.50


def _normalize(text: str) -> str:
    """
    Standardize text for comparison:
    - Lowercase
    - '128 gb' → '128gb' (unit spacing)
    - 's24+' / 's24 plus' → 's24plus' (plus normalization)
    - Strip ad noise
    """
    text = text.lower()
    # Unit spacing: "128 gb" → "128gb"
    text = re.sub(r"(\d)\s+(gb|tb|mb|hz|kg|ml)\b", r"\1\2", text)
    # Plus normalization: "+" and "plus" → "plus" as a word
    text = re.sub(r"\+", " plus ", text)
    text = re.sub(r"\s+", " ", text)
    # Strip ad noise
    for noise in _NOISE_TERMS:
        text = text.replace(noise, " ")
    return text.strip()


def _tokenize(text: str) -> list[str]:
    """Extract meaningful tokens, filtering stopwords and single characters."""
    tokens = re.findall(r"\b\w+\b", _normalize(text))
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _token_weight(token: str) -> float:
    """Specification tokens (model numbers, capacities) are weighted 2x."""
    return 2.0 if _SPEC_PATTERN.match(token) else 1.0


def _relevance_score(query: str, title: str) -> float:
    """
    Weighted relevance ratio: how much of the query (by weight) appears in the title.
    Spec tokens (e.g., '128gb', '5g') carry double weight.
    Returns 0.0–1.0.
    """
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 1.0

    t_tokens = set(_tokenize(title))
    total_weight = sum(_token_weight(t) for t in q_tokens)
    matched_weight = sum(_token_weight(t) for t in q_tokens if t in t_tokens)

    return matched_weight / total_weight if total_weight > 0 else 0.0


def _filter_and_sort(query: str, results: list[dict]) -> list[dict]:
    """
    Filter results below the relevance threshold, then sort by:
    1. relevance score DESC (most relevant first)
    2. price ASC (cheapest within same relevance)
    """
    scored = [
        (r, _relevance_score(query, r.get("title", "")))
        for r in results
    ]
    filtered = [(r, s) for r, s in scored if s >= _RELEVANCE_THRESHOLD]

    removed = len(results) - len(filtered)
    if removed:
        logger.info(
            "Busca | %d resultado(s) descartados por baixa relevância | query='%s'",
            removed, query,
        )

    # Sort: relevance DESC, price ASC (None prices go last)
    filtered.sort(key=lambda x: (-x[1], x[0].get("price") or float("inf")))
    return [r for r, _ in filtered]


def run_product_search(query: str, search_id: str | None = None) -> str:
    """
    Searches for products by name across stores and persists the results.

    Args:
        query:     Search term from the user (e.g. "iPhone 15 128GB").
        search_id: External ID to use (e.g. Celery task ID). Generates UUID if None.

    Returns:
        search_id used for persistence — poll via GET /search/{search_id}.
    """
    if not search_id:
        search_id = str(uuid.uuid4())

    all_results: list[dict] = []

    for search_fn in SEARCH_FUNCTIONS:
        store_name = search_fn.__module__.split(".")[-1]
        try:
            results = search_fn(query, max_results=10)
            logger.info(
                "Busca | store=%s | brutos=%d | query='%s'",
                store_name, len(results), query,
            )
            all_results.extend(results)
        except Exception:
            logger.exception("Busca | store=%s falhou | query='%s'", store_name, query)

    relevant_results = _filter_and_sort(query, all_results)

    saved = save_search_results(search_id, query, relevant_results)
    logger.info(
        "Busca concluída | salvos=%d relevantes=%d brutos=%d | query='%s' | id=%s",
        saved, len(relevant_results), len(all_results), query, search_id,
    )

    return search_id
