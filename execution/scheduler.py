import os

from celery.schedules import crontab

from .worker_tasks import app

# Agendamento de tarefas periódicas via Celery Beat
# Evita falha por falta de argumentos no task agendado.
def _build_schedule() -> dict:
    monitor_url = os.getenv("MONITOR_URL")
    monitor_store = os.getenv("MONITOR_STORE")

    if not monitor_url or not monitor_store:
        return {}

    return {
        "check-prices-every-6-hours": {
            "task": "execution.worker_tasks.process_price_check",
            "schedule": crontab(minute=0, hour="*/6"),  # A cada 6 horas
            "args": (monitor_url, monitor_store),
        }
    }


app.conf.beat_schedule = _build_schedule()
