from celery.schedules import crontab

from .worker_tasks import app


# Agendamento de tarefas periódicas via Celery Beat
app.conf.beat_schedule = {
    "schedule-all-products-every-6-hours": {
        "task": "execution.worker_tasks.schedule_all_products",
        "schedule": crontab(minute=0, hour="*/6"),
    }
}
