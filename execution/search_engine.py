from __future__ import annotations

from urllib.parse import quote_plus

SUPPORTED_AUTOMATIC_SEARCH_STORES: tuple[str, ...] = ("amazon", "mercadolivre", "shopee")


def build_search_url(store: str, query: str) -> str:
    normalized = store.strip().lower()
    encoded_query = quote_plus(query)

    if normalized == "amazon":
        return f"https://www.amazon.com.br/s?k={encoded_query}"
    if normalized == "mercadolivre":
        return f"https://lista.mercadolivre.com.br/{encoded_query}"
    if normalized == "shopee":
        return f"https://shopee.com.br/search?keyword={encoded_query}"

    supported = ", ".join(SUPPORTED_AUTOMATIC_SEARCH_STORES)
    raise ValueError(f"Loja '{store}' não suportada para busca automática. Use: {supported}.")
