import hashlib
import json
import os

import redis
from dotenv import load_dotenv

load_dotenv()

# Conexão com Redis (Usado para Cache e Fila do Celery)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _cache_key(product_url: str) -> str:
    url_hash = hashlib.sha256(product_url.encode("utf-8")).hexdigest()
    return f"price_cache:{url_hash}"


def get_cached_price(product_url: str):
    """Verifica se existe um preço recente no Redis para a URL informada."""
    raw_value = redis_client.get(_cache_key(product_url))
    if not raw_value:
        return None

    try:
        payload = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None

    return payload


def set_cached_price(
    product_url: str,
    price: float,
    name: str | None = None,
    store: str | None = None,
    ttl: int = 7200,
):
    """Salva o snapshot do produto no Redis com TTL padrão de 2 horas."""
    payload = {
        "url": product_url,
        "price": float(price),
        "name": name,
        "store": store,
    }
    redis_client.setex(_cache_key(product_url), ttl, json.dumps(payload))
