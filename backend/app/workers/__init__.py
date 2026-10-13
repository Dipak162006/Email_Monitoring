"""Celery workers package."""
from app.workers.celery_app import celery_app
from app.workers.tasks import (
    sync_all_active_accounts_task,
    sync_email_account_task,
)

__all__ = [
    "celery_app",
    "sync_email_account_task",
    "sync_all_active_accounts_task",
    "dispatch_campaign_task",
]


def __getattr__(name: str):
    if name == "dispatch_campaign_task":
        from app.workers.campaign_tasks import dispatch_campaign_task
        return dispatch_campaign_task
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

