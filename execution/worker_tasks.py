import logging
import os
from typing import Any

from celery import Celery
from dotenv import load_dotenv

from .adapters import normalize_store, parse_product_data
from .cache_manager import get_cached_price, set_cached_price
from .db_client import (
    add_price_history,
    get_all_products,
    get_or_create_product,
    save_automatic_search_results,
)
from .firecrawl_api import scrape_product_data, scrape_search_results
from .search_engine import SUPPORTED_AUTOMATIC_SEARCH_STORES, build_search_url

load_dotenv()

logger = logging.getLogger(__name__)

# Configuração do Worker Celery
app = Celery("tasks", broker=os.getenv("REDIS_URL", "redis://localhost:6379/1"))


def _build_success_payload(
    *,
    source: str,
    url: str,
    store: str,
    price: float,
    name: str | None,
    product_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "source": source,
        "url": url,
        "store": store,
        "name": name,
        "price": float(price),
    }
    if product_id:
        payload["product_id"] = product_id
    return payload


def run_price_pipeline(url: str, store: str) -> dict[str, Any]:
    """Pipeline principal com integração real (Redis, Firecrawl e PostgreSQL)."""
    if not url or not isinstance(url, str):
        raise ValueError("'url' deve ser uma string não vazia.")

    normalized_store = normalize_store(store)

    cached_payload = get_cached_price(url)
    if cached_payload and isinstance(cached_payload.get("price"), (int, float)):
        return _build_success_payload(
            source="cache",
            url=url,
            store=normalized_store,
            price=float(cached_payload["price"]),
            name=cached_payload.get("name"),
        )

    raw_data = scrape_product_data(url)
    if not raw_data:
        return {
            "status": "error",
            "url": url,
            "store": normalized_store,
            "reason": "Falha ao extrair dados no Firecrawl.",
        }

    parsed_data = parse_product_data(normalized_store, raw_data)
    product_name = parsed_data.get("name")
    product_price = parsed_data.get("price")

    if not isinstance(product_price, (int, float)):
        return {
            "status": "error",
            "url": url,
            "store": normalized_store,
            "reason": "Não foi possível extrair um preço numérico válido.",
        }

    product = get_or_create_product(url=url, name=product_name, store=normalized_store)
    add_price_history(product_id=product.id, price=float(product_price))

    set_cached_price(
        product_url=url,
        price=float(product_price),
        name=product_name,
        store=normalized_store,
        ttl=7200,
    )

    return _build_success_payload(
        source="firecrawl",
        url=url,
        store=normalized_store,
        name=product_name,
        price=float(product_price),
        product_id=product.id,
    )


def run_automatic_search_pipeline(query: str, limit: int = 10) -> dict[str, Any]:
    """Busca produtos por nome em múltiplas lojas e salva os resultados no PostgreSQL."""
    normalized_query = (query or "").strip()
    if not normalized_query:
        raise ValueError("'query' deve ser uma string não vazia.")

    max_results = max(1, min(limit, 20))
    summary: dict[str, Any] = {
        "status": "ok",
        "query": normalized_query,
        "limit": max_results,
        "stores": {},
    }

    total_saved = 0

    for store in SUPPORTED_AUTOMATIC_SEARCH_STORES:
        search_url = build_search_url(store, normalized_query)
        products = scrape_search_results(search_url, limit=max_results)

        for index, product in enumerate(products, start=1):
            product["position"] = index

        saved_count = save_automatic_search_results(normalized_query, store, products)
        total_saved += saved_count

        summary["stores"][store] = {
            "search_url": search_url,
            "found": len(products),
            "saved": saved_count,
        }

    summary["saved_total"] = total_saved
    return summary


@app.task
def process_price_check(url: str, store: str) -> dict[str, Any]:
    """Executa o pipeline de checagem com logs estruturados."""
    try:
        return run_price_pipeline(url=url, store=store)
    except Exception as exc:
        logger.exception("Erro no pipeline de preço. url=%s store=%s", url, store)
        return {
            "status": "error",
            "url": url,
            "store": store,
            "reason": str(exc),
        }


@app.task
def automatic_search_products(query: str, limit: int = 10) -> dict[str, Any]:
    """Task Celery para busca automática multi-loja por nome de produto."""
    try:
        return run_automatic_search_pipeline(query=query, limit=limit)
    except Exception as exc:
        logger.exception("Erro na busca automática. query=%s", query)
        return {
            "status": "error",
            "query": query,
            "reason": str(exc),
        }


@app.task
def schedule_all_products() -> dict[str, Any]:
    """Reenfileira todos os produtos cadastrados para nova checagem."""
    products = get_all_products()
    scheduled = 0

    for product in products:
        if not product.url or not product.store:
            continue

        process_price_check.delay(product.url, product.store)
        scheduled += 1

    return {
        "status": "ok",
        "scheduled_products": scheduled,
    }


# Importa o agendamento para que o Celery Beat o reconheça
from . import scheduler
