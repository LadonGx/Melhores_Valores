"""
Saúde das lojas — último sucesso e última falha por loja e por canal.

Canais:
  - "search":  busca por nome (search_orchestrator)
  - "monitor": verificação de preço de um anúncio (scraping_orchestrator)

Os canais são separados porque uma loja pode bloquear um e não o outro
(ex.: Mercado Livre exige login na busca, mas a página do anúncio continua acessível).

Gravação é "best effort": qualquer erro de Redis é engolido e logado — nunca
interrompe uma busca ou um scraping.
"""
import logging
from datetime import datetime, timezone

from .cache_manager import redis_client

logger = logging.getLogger(__name__)

STORES: dict[str, str] = {
    "amazon": "Amazon",
    "mercadolivre": "Mercado Livre",
}
CHANNELS = ("search", "monitor")

# Mensagens curtas para o usuário, por categoria de bloqueio
_CATEGORY_LABELS: dict[str, str] = {
    "login_wall": "exigindo login",
    "access_denied": "acesso negado",
    "captcha": "pedindo captcha",
    "error": "falhando",
}


def _key(store: str, channel: str) -> str:
    return f"store_health:{store}:{channel}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_ok(store: str | None, channel: str) -> None:
    """Registra que a loja respondeu normalmente neste canal."""
    if store not in STORES or channel not in CHANNELS:
        return
    try:
        redis_client.hset(_key(store, channel), mapping={"last_ok_at": _now_iso()})
    except Exception:  # noqa: BLE001 — saúde é informativa, nunca quebra o fluxo
        logger.warning("store_health: falha ao gravar sucesso | store=%s channel=%s", store, channel)


def record_failure(store: str | None, channel: str, category: str | None = None) -> None:
    """Registra uma falha (bloqueio com categoria, ou erro genérico) neste canal."""
    if store not in STORES or channel not in CHANNELS:
        return
    try:
        redis_client.hset(
            _key(store, channel),
            mapping={"last_fail_at": _now_iso(), "last_fail_category": category or "error"},
        )
    except Exception:  # noqa: BLE001
        logger.warning("store_health: falha ao gravar erro | store=%s channel=%s", store, channel)


def _decode(raw: dict) -> dict[str, str]:
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


def _channel_status(data: dict[str, str]) -> dict:
    last_ok = data.get("last_ok_at")
    last_fail = data.get("last_fail_at")
    category = data.get("last_fail_category")

    if last_fail and (not last_ok or last_fail > last_ok):
        status = "error" if category in (None, "error") else "blocked"
        detail = _CATEGORY_LABELS.get(category or "error", "falhando")
    elif last_ok:
        status, detail = "ok", "funcionando"
    else:
        status, detail = "unknown", "sem verificações recentes"

    return {
        "status": status,
        "detail": detail,
        "category": category if status in ("blocked", "error") else None,
        "last_ok_at": last_ok,
        "last_fail_at": last_fail,
    }


_SEVERITY = {"ok": 0, "unknown": 1, "error": 2, "blocked": 3}


def get_stores_health() -> list[dict]:
    """Status por loja: geral (pior canal) + detalhe de cada canal."""
    stores = []
    for store, label in STORES.items():
        channels = {}
        for channel in CHANNELS:
            try:
                raw = redis_client.hgetall(_key(store, channel))
            except Exception:  # noqa: BLE001
                raw = {}
            channels[channel] = _channel_status(_decode(raw))

        known = [c["status"] for c in channels.values() if c["status"] != "unknown"]
        if not known:
            overall = "unknown"
        else:
            overall = max(known, key=lambda s: _SEVERITY[s])
            # Um canal bom e outro com problema = loja "parcial", não "fora do ar"
            if overall != "ok" and "ok" in known:
                overall = "partial"

        stores.append({"store": store, "label": label, "status": overall, "channels": channels})
    return stores
