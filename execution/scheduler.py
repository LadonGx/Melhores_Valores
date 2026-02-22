from .worker_tasks import app
from celery.schedules import crontab

# Agendamento de tarefas periódicas via Celery Beat
app.conf.beat_schedule = {
    'check-prices-every-6-hours': {
        'task': 'execution.worker_tasks.process_price_check',
        'schedule': crontab(minute=0, hour='*/6'), # A cada 6 horas
    },
}
