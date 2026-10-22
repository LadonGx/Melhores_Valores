import json

from .cache_manager import memory_cache

# Tempo suficiente para o usuário conferir o resultado de uma busca recém-feita.
_TTL = 1800


def _key(search_id: str) -> str:
    return f"search_warnings:{search_id}"


def set_search_warnings(search_id: str, warnings: dict[str, str]) -> None:
    """Persiste, por um tempo curto, quais lojas foram bloqueadas numa busca."""
    if not warnings:
        return
    memory_cache.setex(_key(search_id), _TTL, json.dumps(warnings))


def get_search_warnings(search_id: str) -> dict[str, str]:
    """Retorna as lojas bloqueadas de uma busca, ou {} se não houve bloqueio/expirou."""
    raw_value = memory_cache.get(_key(search_id))
    if not raw_value:
        return {}

    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}
