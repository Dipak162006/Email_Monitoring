from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import Campaign, CampaignStatus

logger = logging.getLogger(__name__)


class CampaignSchedulingService:
    """Service handling discovery, validation, and safe dispatch of due SCHEDULED campaigns."""

    @classmethod
    async def get_due_scheduled_campaigns(
        cls,
        db: AsyncSession,
        now_utc: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Campaign]:
        """Find campaigns in SCHEDULED status whose scheduled_at is less than or equal to now_utc.
        
        Uses row-level locking (with_for_update with skip_locked=True) to ensure multiple
        concurrent scheduler ticks do not pick up the same campaigns.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        stmt = (
            select(Campaign)
            .where(
                Campaign.status == CampaignStatus.SCHEDULED.value,
                Campaign.scheduled_at.is_not(None),
                Campaign.scheduled_at <= now_utc,
            )
            .order_by(Campaign.scheduled_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def dispatch_due_campaigns(
        cls,
        db_factory=None,
        now_utc: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Identify due SCHEDULED campaigns across companies and dispatch them safely.
        
        Guarantees:
        - Only processes campaigns where status == SCHEDULED and scheduled_at <= now_utc
        - Employs row-level locking (with_for_update skip_locked=True) and atomic state transition
        - Safe against duplicate scheduler ticks (once QUEUED, cannot be matched again)
        - Tenant isolation preserved per campaign
        - Never sends email directly; delegates to CampaignDispatchService
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        # Step 1: Discover due campaign candidates under short read transaction
        async with db_factory() as db:
            stmt = (
                select(Campaign.id, Campaign.company_id, Campaign.scheduled_at)
                .where(
                    Campaign.status == CampaignStatus.SCHEDULED.value,
                    Campaign.scheduled_at.is_not(None),
                    Campaign.scheduled_at <= now_utc,
                )
                .order_by(Campaign.scheduled_at.asc())
            )
            res = await db.execute(stmt)
            candidates = res.all()

        results: List[Dict[str, Any]] = []
        for camp_id, comp_id, camp_sched in candidates:
            outcome = await cls.dispatch_scheduled_campaign(
                campaign_id=camp_id,
                company_id=comp_id,
                db_factory=db_factory,
                now_utc=now_utc,
            )
            results.append(outcome)

        return results

    @classmethod
    async def dispatch_scheduled_campaign(
        cls,
        campaign_id: int,
        company_id: int,
        db_factory=None,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Dispatch an individual scheduled campaign safely with row-level locking and validation.
        
        Workflow:
        1. Select campaign with row lock (with_for_update(skip_locked=True))
        2. Verify status is SCHEDULED and scheduled_at has arrived
        3. Delegate to CampaignDispatchService for preflight, atomic transition to QUEUED, and Celery enqueuing
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        async with db_factory() as db:
            stmt = (
                select(Campaign)
                .where(
                    Campaign.id == campaign_id,
                    Campaign.company_id == company_id,
                )
                .with_for_update(skip_locked=True)
            )
            res = await db.execute(stmt)
            campaign = res.scalar_one_or_none()

            if not campaign:
                logger.info(
                    "Scheduled campaign %d (company %d) is locked or not found. Skipping.",
                    campaign_id,
                    company_id,
                )
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "SKIPPED",
                    "reason": "Campaign locked by another worker or not found.",
                }

            if campaign.status != CampaignStatus.SCHEDULED.value:
                logger.info(
                    "Scheduled campaign %d has status '%s' (expected SCHEDULED). Skipping.",
                    campaign_id,
                    campaign.status,
                )
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "SKIPPED",
                    "reason": f"Expected SCHEDULED status, found '{campaign.status}'.",
                }

            sched_time = campaign.scheduled_at
            if sched_time is None:
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "SKIPPED",
                    "reason": "Campaign has no scheduled_at timestamp.",
                }

            if sched_time.tzinfo is None:
                sched_time = sched_time.replace(tzinfo=timezone.utc)

            if sched_time > now_utc:
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "SKIPPED",
                    "reason": "Campaign scheduled_at has not arrived yet.",
                }

            from app.modules.campaigns.dispatch_service import CampaignDispatchService
            try:
                dispatch_res = await CampaignDispatchService.dispatch_scheduled_campaign(
                    db=db,
                    company_id=company_id,
                    campaign_id=campaign_id,
                )
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "DISPATCHED",
                    "task_id": dispatch_res.task_id,
                }
            except Exception as exc:
                logger.error("Failed to dispatch scheduled campaign %d: %s", campaign_id, exc)
                return {
                    "campaign_id": campaign_id,
                    "company_id": company_id,
                    "status": "FAILED",
                    "error": str(exc),
                }

    @classmethod
    async def recover_due_paced_campaigns(
        cls,
        db_factory=None,
        now_utc: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Recover due RUNNING campaigns whose next_send_at has arrived.
        
        Guarantees:
        - Recovers lost Celery countdown tasks after worker restarts or Redis interruptions.
        - Row-level lock with skip_locked=True prevents duplicate task execution.
        - Verifies remaining pending recipients before enqueuing.
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        recovered: List[Dict[str, Any]] = []
        async with db_factory() as db:
            from sqlalchemy import func
            from app.modules.campaigns.models import CampaignRecipient, CampaignRecipientStatus
            stmt = (
                select(Campaign.id, Campaign.company_id, Campaign.next_send_at)
                .where(
                    Campaign.status == CampaignStatus.RUNNING.value,
                    Campaign.send_interval_seconds > 0,
                    Campaign.next_send_at.is_not(None),
                    Campaign.next_send_at <= now_utc,
                )
                .order_by(Campaign.next_send_at.asc())
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            res = await db.execute(stmt)
            due_campaigns = res.all()

            for camp_id, comp_id, next_send in due_campaigns:
                pending_cnt = await db.scalar(
                    select(func.count(CampaignRecipient.id)).where(
                        CampaignRecipient.campaign_id == camp_id,
                        CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
                    )
                ) or 0
                if pending_cnt > 0:
                    from app.workers.campaign_tasks import dispatch_campaign_task
                    try:
                        dispatch_campaign_task.delay(
                            campaign_id=camp_id,
                            company_id=comp_id,
                        )
                        recovered.append({
                            "campaign_id": camp_id,
                            "company_id": comp_id,
                            "status": "ENQUEUED",
                            "pending_recipients": pending_cnt,
                        })
                    except Exception as exc:
                        logger.warning("Could not enqueue recovery task for campaign %d: %s", camp_id, exc)

        return recovered

    @classmethod
    async def recover_stale_sending_deliveries(
        cls,
        db_factory=None,
        now_utc: Optional[datetime] = None,
        stale_minutes: int = 10,
    ) -> List[Dict[str, Any]]:
        """Recover stale SENDING deliveries caused by crashed workers or ungraceful task termination.
        
        Guarantees:
        - Finds CampaignDelivery rows in SENDING status with last_attempt_at <= (now_utc - stale_minutes).
        - Uses row-level lock (with_for_update skip_locked=True) to safely isolate recovery.
        - Transitions delivery to FAILED with error_message='Delivery timed out or worker interrupted while sending.'
        - Updates associated CampaignRecipient to FAILED if still PENDING.
        - Returns list of recovered delivery descriptors for observability.
        """
        if db_factory is None:
            from app.workers.tasks import get_worker_db
            db_factory = get_worker_db

        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        from datetime import timedelta
        from app.modules.campaigns.models import (
            CampaignDelivery,
            CampaignDeliveryStatus,
            CampaignRecipient,
            CampaignRecipientStatus,
        )

        stale_cutoff = now_utc - timedelta(minutes=stale_minutes)
        recovered: List[Dict[str, Any]] = []

        async with db_factory() as db:
            stmt = (
                select(CampaignDelivery)
                .where(
                    CampaignDelivery.status == CampaignDeliveryStatus.SENDING.value,
                    CampaignDelivery.last_attempt_at.is_not(None),
                    CampaignDelivery.last_attempt_at <= stale_cutoff,
                )
                .order_by(CampaignDelivery.last_attempt_at.asc())
                .with_for_update(skip_locked=True)
            )
            res = await db.execute(stmt)
            stale_deliveries = list(res.scalars().all())

            for deliv in stale_deliveries:
                deliv.status = CampaignDeliveryStatus.FAILED.value
                deliv.error_message = "Delivery timed out or worker interrupted while sending."

                # Update associated CampaignRecipient if still in PENDING
                if deliv.recipient_id:
                    recip_stmt = select(CampaignRecipient).where(
                        CampaignRecipient.id == deliv.recipient_id,
                        CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
                    )
                    recip_res = await db.execute(recip_stmt)
                    recip = recip_res.scalar_one_or_none()
                    if recip:
                        recip.status = CampaignRecipientStatus.FAILED.value

                recovered.append({
                    "delivery_id": deliv.id,
                    "campaign_id": deliv.campaign_id,
                    "recipient_id": deliv.recipient_id,
                    "last_attempt_at": deliv.last_attempt_at.isoformat() if deliv.last_attempt_at else None,
                })

            if stale_deliveries:
                await db.commit()
                logger.info(
                    "Recovered %d stale SENDING deliveries older than %d minutes.",
                    len(stale_deliveries),
                    stale_minutes,
                )

        return recovered

