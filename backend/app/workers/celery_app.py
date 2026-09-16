from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "email_monitoring_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
)

if settings.SYNC_INTERVAL_MINUTES > 0:
    celery_app.conf.beat_schedule = {
        "sync-active-email-accounts-periodic": {
            "task": "app.workers.tasks.sync_all_active_accounts_task",
            "schedule": crontab(minute=f"*/{settings.SYNC_INTERVAL_MINUTES}"),
        },
    }

