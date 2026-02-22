import asyncio
import os
from typing import Callable, Optional

from celery import Celery
from dotenv import load_dotenv

from .adapters.aliexpress import extract_name as aliexpress_extract_name
from .adapters.aliexpress import extract_price as aliexpress_extract_price
from .adapters.amazon import extract_name as amazon_extract_name
from .adapters.amazon import extract_price as amazon_extract_price
from .adapters.mercadolivre import extract_name as mercadolivre_extract_name
from .adapters.mercadolivre import extract_price as mercadolivre_extract_price
from .cache_manager import get_cached_price, set_cached_price
from .db_client import connect_db, db, disconnect_db
from .firecrawl_api import scrape_product_data

load_dotenv()

# Configuração do Worker Celery
app = Celery("tasks", broker=os.getenv("REDIS_URL", "redis://localhost:6379/1"))


AdapterTuple = tuple[Callable, Callable]


def _select_adapter(store: str) -> Optional[AdapterTuple]:
    store_map = {
        "amazon": (amazon_extract_price, amazon_extract_name),
        "mercadolivre": (mercadolivre_extract_price, mercadolivre_extract_name),
        "aliexpress": (aliexpress_extract_price, aliexpress_extract_name),
    }
    return store_map.get(store.lower())


async def _persist_price(url: str, store: str, name: str, price: float) -> None:
    await connect_db()
    try:
        product = await db.product.upsert(
            where={"url": url},
            data={
                "create": {"name": name, "url": url, "store": store},
                "update": {"name": name, "store": store},
            },
        )
        await db.pricehistory.create(
            data={
                "price": float(price),
                "productId": product.id,
            }
        )
    finally:
        await disconnect_db()


@app.task
def process_price_check(url: str, store: str):
    """
    Pipeline Principal:
    1. Verifica Cache (cache_manager)
    2. Se vazio, chama Firecrawl (firecrawl_api)
    3. Processa via Adapter (adapters/)
    4. Salva no Banco (db_client)
    5. Atualiza o Cache
    """
    if not url or not store:
        return {"status": "ignored", "reason": "missing_url_or_store"}

    cached = get_cached_price(url)
    if cached:
        return {"status": "cache_hit", "data": cached}

    raw_data = scrape_product_data(url)
    if not raw_data:
        return {"status": "error", "reason": "firecrawl_empty_response"}

    adapter = _select_adapter(store)
    if not adapter:
        return {"status": "error", "reason": f"unsupported_store:{store}"}

    extract_price, extract_name = adapter
    price = extract_price(raw_data)
    name = extract_name(raw_data) or url

    if price is None:
        return {"status": "error", "reason": "price_not_found"}

    asyncio.run(_persist_price(url=url, store=store, name=name, price=float(price)))
    set_cached_price(url, float(price))
    return {"status": "ok", "url": url, "store": store, "name": name, "price": float(price)}


# Importa o agendamento para que o Celery Beat o reconheça
from . import scheduler
