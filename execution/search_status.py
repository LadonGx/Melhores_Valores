import json

from .cache_manager import redis_client

# Tempo suficiente para o usuário conferir o resultado de uma busca recém-feita.
_TTL = 1800


def _key(search_id: str) -> str:
    return f"search_warnings:{search_id}"


def set_search_warnings(search_id: str, warnings: dict[str, str]) -> None:
    """Persiste, por um tempo curto, quais lojas foram bloqueadas numa busca."""
    if not warnings:
        return
    redis_client.setex(_key(search_id), _TTL, json.dumps(warnings))


def get_search_warnings(search_id: str) -> dict[str, str]:
    """Retorna as lojas bloqueadas de uma busca, ou {} se não houve bloqueio/expirou."""
    raw_value = redis_client.get(_key(search_id))
    if not raw_value:
        return {}

    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}
