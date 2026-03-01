import logging
import os
from typing import Any

from celery import Celery
from dotenv import load_dotenv

from .adapters import normalize_store, parse_product_data
from .cache_manager import get_cached_price, set_cached_price
from .db_client import add_price_history, get_all_products, get_or_create_product
from .firecrawl_api import scrape_product_data

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
