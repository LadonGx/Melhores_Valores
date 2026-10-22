"""
Agendador da checagem periódica de preços, no lugar do Celery Beat.

O app desktop só roda enquanto está aberto, então "a cada 6h desde que o app
abriu" não basta: quem abre o app por 20 minutos por dia nunca chegaria às 6h.
Por isso o horário da última checagem completa fica no banco (AppMeta) e, ao
abrir, a próxima rodada é marcada para última + 6h — ou para daqui a pouco,
se esse horário já passou.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .db_client import get_last_full_check, set_last_full_check
from .worker_tasks import schedule_all_products

logger = logging.getLogger(__name__)

CHECK_INTERVAL = timedelta(hours=6)
# Atraso da rodada de recuperação, para não disputar recursos com a abertura da UI
CATCH_UP_DELAY = timedelta(minutes=1)

_JOB_ID = "full-price-check"
_scheduler: BackgroundScheduler | None = None


def next_full_check_at(last: datetime | None, now: datetime) -> datetime:
    """Quando a próxima checagem completa deve rodar."""
    if last is None or now - last >= CHECK_INTERVAL:
        return now + CATCH_UP_DELAY
    return last + CHECK_INTERVAL


def run_full_check() -> dict:
    """Reenfileira todos os produtos ativos e registra o horário da rodada."""
    result = schedule_all_products()
    set_last_full_check(datetime.now(timezone.utc))
    logger.info("Checagem completa disparada | produtos=%s", result.get("scheduled_products"))
    return result


def start() -> None:
    """Liga o agendador (idempotente). Chamado na subida do app."""
    global _scheduler
    if _scheduler is not None:
        return

    first_run = next_full_check_at(get_last_full_check(), datetime.now(timezone.utc))
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        run_full_check,
        "interval",
        seconds=int(CHECK_INTERVAL.total_seconds()),
        next_run_time=first_run,
        id=_JOB_ID,
        max_instances=1,
        coalesce=True,
        # Se o PC dormir e acordar depois do horário, roda assim que acordar
        misfire_grace_time=None,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Agendador iniciado | intervalo=%s | próxima checagem completa=%s",
        CHECK_INTERVAL, first_run.isoformat(timespec="seconds"),
    )


def shutdown() -> None:
    """Desliga o agendador (no fechamento do app)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Agendador encerrado")
