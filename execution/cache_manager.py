import hashlib
import json
import threading
import time
from typing import Any, Callable


class TTLCache:
    """
    Substituto em memória do Redis para o app desktop (processo único).
    Expõe só o que o projeto usava do Redis (get / setex) e é thread-safe,
    já que API e workers rodam em threads do mesmo processo.

    O conteúdo se perde ao fechar o app — aceitável, o cache é só otimização.
    """

    # Acima deste tamanho, cada setex varre e descarta as chaves expiradas
    _PRUNE_THRESHOLD = 1024

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if self._clock() >= expires_at:
                del self._data[key]
                return None
            return value

    def setex(self, key: str, ttl: int, value: Any) -> None:
        with self._lock:
            now = self._clock()
            self._data[key] = (now + ttl, value)
            if len(self._data) > self._PRUNE_THRESHOLD:
                self._data = {k: v for k, v in self._data.items() if v[0] > now}

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# Cache compartilhado pelo processo (preços e avisos de busca)
memory_cache = TTLCache()


def _cache_key(product_url: str) -> str:
    url_hash = hashlib.sha256(product_url.encode("utf-8")).hexdigest()
    return f"price_cache:{url_hash}"


def get_cached_price(product_url: str):
    """Verifica se existe um preço recente em cache para a URL informada."""
    raw_value = memory_cache.get(_cache_key(product_url))
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
    """Salva o snapshot do produto em cache com TTL padrão de 2 horas."""
    payload = {
        "url": product_url,
        "price": float(price),
        "name": name,
        "store": store,
    }
    # Guardado como JSON (como no Redis): quem lê recebe sempre uma cópia nova,
    # então alterar o dict retornado não altera o cache.
    memory_cache.setex(_cache_key(product_url), ttl, json.dumps(payload))
