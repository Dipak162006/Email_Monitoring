import logging
from typing import Any, Dict, Optional

from app.modules.campaigns.delivery_service import CampaignDeliveryService
from app.workers.celery_app import celery_app
from app.workers.tasks import run_async

logger = logging.getLogger(__name__)


async def _async_dispatch_campaign_task(campaign_id: int, company_id: int) -> Dict[str, Any]:
    """Asynchronous core of the campaign dispatch Celery worker task.
    
    Executes the campaign delivery engine for the specified campaign.
    """
    logger.info(
        "Executing background campaign delivery worker task for campaign_id=%d, company_id=%d",
        campaign_id,
        company_id,
    )
    try:
        return await CampaignDeliveryService.execute_campaign(
            campaign_id=campaign_id,
            company_id=company_id,
        )
    except Exception as exc:
        logger.exception(
            "Unhandled failure in campaign delivery task for campaign_id=%d, company_id=%d: %s",
            campaign_id,
            company_id,
            exc,
        )
        raise


@celery_app.task(
    bind=True,
    name="app.workers.campaign_tasks.dispatch_campaign_task",
    acks_late=True,
)
def dispatch_campaign_task(self, campaign_id: int, company_id: int) -> Dict[str, Any]:
    """Celery task responsible for executing campaign delivery."""
    return run_async(_async_dispatch_campaign_task(campaign_id=campaign_id, company_id=company_id))


async def _async_retry_campaign_delivery_task(delivery_id: int, company_id: int) -> Dict[str, Any]:
    """Asynchronous core of the campaign delivery retry Celery worker task."""
    logger.info(
        "Executing background campaign delivery retry for delivery_id=%d, company_id=%d",
        delivery_id,
        company_id,
    )
    try:
        return await CampaignDeliveryService.retry_delivery(
            delivery_id=delivery_id,
            company_id=company_id,
        )
    except Exception as exc:
        logger.exception(
            "Unhandled failure in campaign delivery retry task for delivery_id=%d, company_id=%d: %s",
            delivery_id,
            company_id,
            exc,
        )
        raise


@celery_app.task(
    bind=True,
    name="app.workers.campaign_tasks.retry_campaign_delivery_task",
    acks_late=True,
)
def retry_campaign_delivery_task(self, delivery_id: int, company_id: int) -> Dict[str, Any]:
    """Celery task responsible for retrying an individual failed campaign delivery."""
    return run_async(_async_retry_campaign_delivery_task(delivery_id=delivery_id, company_id=company_id))


async def _async_scheduled_campaign_dispatch_task() -> Dict[str, Any]:
    """Asynchronous core of the scheduled campaign dispatch periodic Celery task."""
    logger.info("Executing periodic scheduled campaign dispatch check.")
    try:
        from app.modules.campaigns.scheduling_service import CampaignSchedulingService
        dispatched = await CampaignSchedulingService.dispatch_due_campaigns()
        recovered = await CampaignSchedulingService.recover_due_paced_campaigns()
        stale_deliveries = await CampaignSchedulingService.recover_stale_sending_deliveries()
        followups_processed = await CampaignDeliveryService.process_due_followup_steps()
        finalized_campaigns = await CampaignDeliveryService.check_and_finalize_all_running_campaigns()
        return {
            "dispatched_count": len(dispatched),
            "dispatched": dispatched,
            "recovered_count": len(recovered),
            "recovered": recovered,
            "stale_deliveries_count": len(stale_deliveries),
            "stale_deliveries": stale_deliveries,
            "followups_processed_count": len(followups_processed),
            "followups_processed": followups_processed,
            "finalized_campaigns_count": len(finalized_campaigns),
            "finalized_campaigns": finalized_campaigns,
        }
    except Exception as exc:
        logger.exception("Unhandled failure in periodic scheduled campaign dispatch task: %s", exc)
        raise


@celery_app.task(
    bind=True,
    name="app.workers.campaign_tasks.scheduled_campaign_dispatch_task",
    acks_late=True,
)
def scheduled_campaign_dispatch_task(self) -> Dict[str, Any]:
    """Celery periodic task checking and dispatching due scheduled campaigns."""
    return run_async(_async_scheduled_campaign_dispatch_task())


async def _async_sync_remote_unsubscribes_task() -> Dict[str, Any]:
    """Asynchronous core of the remote unsubscribe periodic synchronization task."""
    logger.info("Executing periodic remote unsubscribe synchronization task.")
    try:
        from app.modules.campaigns.unsubscribe_service import UnsubscribeService
        from app.workers.tasks import get_worker_db
        async with get_worker_db() as db:
            synced_count = await UnsubscribeService.sync_remote_unsubscribes(db=db)
            return {"status": "SUCCESS", "synced_count": synced_count}
    except Exception as exc:
        logger.exception("Error in periodic remote unsubscribe synchronization: %s", exc)
        return {"status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.workers.campaign_tasks.sync_remote_unsubscribes_task",
    acks_late=True,
)
def sync_remote_unsubscribes_task(self) -> Dict[str, Any]:
    """Celery periodic task synchronizing remote tracking unsubscribes into local suppression."""
    return run_async(_async_sync_remote_unsubscribes_task())


async def _async_sync_tracking_events_task() -> Dict[str, Any]:
    """Asynchronous core of the interaction tracking events periodic synchronization task."""
    logger.info("Executing periodic remote interaction tracking events synchronization task.")
    try:
        from app.modules.campaigns.tracking_sync_service import TrackingEventSyncService
        from app.workers.tasks import get_worker_db
        async with get_worker_db() as db:
            synced_count = await TrackingEventSyncService.sync_tracking_events(db=db)
            return {"status": "SUCCESS", "synced_count": synced_count}
    except Exception as exc:
        logger.exception("Error in periodic interaction tracking events synchronization: %s", exc)
        return {"status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.workers.campaign_tasks.sync_tracking_events_task",
    acks_late=True,
)
def sync_tracking_events_task(self) -> Dict[str, Any]:
    """Celery periodic task synchronizing remote OPEN and CLICK tracking events into local database."""
    return run_async(_async_sync_tracking_events_task())



