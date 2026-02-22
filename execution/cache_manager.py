import redis
import os
from dotenv import load_dotenv

load_dotenv()

# Conexão com Redis (Usado para Cache e Fila do Celery)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

def get_cached_price(product_url: str):
    """Verifica se existe um preço recente no Redis para a URL informada."""
    # TODO: Implementar lógica de busca por chave (ex: hash da URL)
    return None

def set_cached_price(product_url: str, price: float, ttl: int = 3600):
    """Salva o preço no Redis com um tempo de vida (TTL) padrão de 1 hora."""
    # TODO: Salvar no Redis
    pass
