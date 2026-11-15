"""
Trava global por loja — garante que nunca haja 2 checagens do Mercado Livre ao mesmo tempo.

Por que existe: o Mercado Livre bloqueia (login_wall) quando recebe várias páginas em sequência
curta do mesmo navegador/IP. Worker (`--concurrency=2`) e API (botão "Atualizar preço") passam
pelo `scraping_orchestrator`, então a trava fica lá: uma única trava no Redis serve os dois.

Regras:
  - Só o Mercado Livre usa trava (`LOCKED_STORES`); as outras lojas passam direto, sem tocar no Redis.
  - A trava expira sozinha em `ML_LOCK_TIMEOUT_S` (padrão 300 s) — proteção contra processo morto.
  - Quem não consegue a trava dentro de `wait_s` recebe `StoreBusyError`.
  - Redis fora do ar: a checagem segue SEM trava e um aviso é logado. A disponibilidade do
    monitoramento vale mais que a trava (sem Redis o cache e o broker também estão fora, então
    na prática só acontece em falha parcial) e o perfil persistente do navegador tem a própria
    proteção contra uso simultâneo (A2).
"""
import logging
import os
from contextlib import contextmanager
from typing import Iterator

from .cache_manager import redis_client

logger = logging.getLogger(__name__)

# Lojas que exigem exclusão mútua entre checagens.
LOCKED_STORES = frozenset({"mercadolivre"})

DEFAULT_LOCK_TIMEOUT_S = 300.0
# Espera padrão quando o chamador não informa `lock_wait_s` (ex.: botão "Atualizar preço").
DEFAULT_LOCK_WAIT_S = 60.0


class StoreBusyError(Exception):
    """Outra checagem da mesma loja está em andamento e a espera esgotou."""


def lock_timeout_s() -> float:
    """Expiração da trava (`ML_LOCK_TIMEOUT_S`); valor inválido ou não positivo volta ao padrão."""
    raw = os.getenv("ML_LOCK_TIMEOUT_S")
    if raw is None or not raw.strip():
        return DEFAULT_LOCK_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if value <= 0:
        logger.warning(
            "ML_LOCK_TIMEOUT_S inválida (%r) — usando o padrão %.0f s", raw, DEFAULT_LOCK_TIMEOUT_S
        )
        return DEFAULT_LOCK_TIMEOUT_S
    return value


def _lock_name(store: str) -> str:
    return f"store_lock:{store}"


@contextmanager
def store_check_lock(store: str | None, wait_s: float | None = None) -> Iterator[None]:
    """Segura a trava global da loja durante o bloco `with`.

    Args:
        store: loja da checagem; as que não estão em `LOCKED_STORES` passam direto.
        wait_s: espera máxima pela trava, em segundos (None → `DEFAULT_LOCK_WAIT_S`).

    Raises:
        StoreBusyError: a trava continuou ocupada durante `wait_s`.
    """
    if store not in LOCKED_STORES:
        yield
        return

    wait = DEFAULT_LOCK_WAIT_S if wait_s is None else max(float(wait_s), 0.0)
    lock = None
    acquired = False
    redis_down = False
    try:
        lock = redis_client.lock(_lock_name(store), timeout=lock_timeout_s(), blocking_timeout=wait)
        acquired = bool(lock.acquire(blocking=True))
    except Exception:  # noqa: BLE001 — Redis fora do ar: segue sem trava (ver docstring do módulo)
        redis_down = True
        logger.warning(
            "Trava da loja indisponível (Redis fora?) — checagem segue SEM trava | store=%s",
            store,
            exc_info=True,
        )

    if redis_down:
        yield
        return

    if not acquired:
        raise StoreBusyError(f"Outra checagem de {store} está em andamento (espera de {wait:.0f}s esgotada).")

    try:
        yield
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001 — expirou (checagem longa) ou Redis caiu: nada a fazer
            logger.warning("Não foi possível liberar a trava da loja | store=%s", store, exc_info=True)
