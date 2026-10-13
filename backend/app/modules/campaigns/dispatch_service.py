from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.modules.campaigns.preflight_service import CampaignPreflightService
from app.modules.campaigns.schemas import CampaignDispatchResponse
from app.modules.campaigns.service import CampaignService, TERMINAL_STATES
from app.modules.campaigns.suppression_service import SuppressionService
from app.workers.campaign_tasks import dispatch_campaign_task

logger = logging.getLogger(__name__)


class CampaignDispatchService:
    """Service orchestrating campaign dispatch validation, state transition, and Celery task enqueuing."""

    @staticmethod
    async def dispatch_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        current_user: User,
        user_role: str,
    ) -> CampaignDispatchResponse:
        """Asynchronously dispatch an eligible campaign for execution.

        Workflow:
        1. Tenant-isolated campaign retrieval with row locking (with_for_update)
        2. State eligibility verification (prevents duplicate dispatch & invalid states)
        3. Preflight eligibility evaluation (reuses C5 CampaignPreflightService)
        4. State transition to QUEUED (via centralized C2 CampaignService.transition_state)
        5. Enqueue Celery task (dispatch_campaign_task.delay)
        6. Return structured CampaignDispatchResponse

        Safety guarantees:
        - Strict tenant isolation (anti-enumeration 404 for wrong company)
        - Preflight must report eligible == True
        - Database state is committed to QUEUED before worker task starts
        - If Celery broker fails, state is reverted to previous state
        - Zero SMTP calls, zero EmailTransport.send(), zero CampaignDelivery rows created
        """
        # 1. Authorization check
        if user_role not in ("OWNER", "ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only company Owners and Admins can dispatch campaigns.",
            )

        # 2. Tenant-isolated campaign retrieval under row-level lock
        # with_for_update prevents concurrent requests from race conditions
        stmt = (
            select(Campaign)
            .where(
                Campaign.id == campaign_id,
                Campaign.company_id == company_id,
            )
            .with_for_update()
        )
        result = await db.execute(stmt)
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found.",
            )

        # 3. State eligibility verification
        if campaign.status == CampaignStatus.QUEUED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign is already queued for execution.",
            )

        if campaign.status == CampaignStatus.RUNNING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign is currently running.",
            )

        if campaign.status in TERMINAL_STATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot dispatch campaign in terminal state '{campaign.status}'.",
            )

        if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot dispatch campaign with status '{campaign.status}'. Only DRAFT or SCHEDULED campaigns can be dispatched.",
            )

        # 4. Preflight eligibility evaluation (reuses C5 preflight service)
        preflight = await CampaignPreflightService.validate_campaign(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            current_user=current_user,
            user_role=user_role,
        )

        if not preflight.eligible:
            blocking_reasons = [issue.message for issue in preflight.issues if issue.blocking]
            reason_str = "; ".join(blocking_reasons) if blocking_reasons else "Campaign is not eligible for execution."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Campaign preflight validation failed: {reason_str}",
            )

        prev_status = campaign.status

        # 5. Mark pre-suppressed recipients as SUPPRESSED upon dispatch
        recip_stmt = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
        )
        recip_res = await db.execute(recip_stmt)
        pending_recips = list(recip_res.scalars().all())
        if pending_recips:
            emails = {r.email for r in pending_recips}
            suppressed_emails = await SuppressionService.get_suppressed_emails(
                db=db,
                company_id=company_id,
                emails=emails,
            )
            for r in pending_recips:
                if r.email.strip().lower() in suppressed_emails:
                    r.status = CampaignRecipientStatus.SUPPRESSED.value

        # 6. State transition to QUEUED using centralized state machine
        campaign = await CampaignService.transition_state(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            target_status=CampaignStatus.QUEUED,
        )

        # 6. Enqueue Celery task with stable, serializable primitives
        task_id: Optional[str] = None
        try:
            task = dispatch_campaign_task.delay(
                campaign_id=campaign.id,
                company_id=campaign.company_id,
            )
            if task and hasattr(task, "id"):
                task_id = str(task.id)
            logger.info(
                "Dispatched campaign %d for company %d (Celery task_id: %s)",
                campaign.id,
                campaign.company_id,
                task_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to enqueue Celery task for campaign %d: %s. Reverting state to %s.",
                campaign.id,
                exc,
                prev_status,
            )
            # Revert campaign status to avoid leaving orphaned QUEUED state
            campaign.status = prev_status
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to enqueue background dispatch task. Campaign returned to previous state.",
            )

        dispatched_at = datetime.now(timezone.utc)

        return CampaignDispatchResponse(
            campaign_id=campaign.id,
            company_id=campaign.company_id,
            status=CampaignStatus.QUEUED,
            task_id=task_id,
            dispatched_at=dispatched_at,
            eligible_recipient_count=preflight.eligible_recipient_count,
            total_recipient_count=preflight.recipient_count,
        )

    @staticmethod
    async def dispatch_scheduled_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> CampaignDispatchResponse:
        """Asynchronously dispatch a due SCHEDULED campaign triggered by the scheduler.

        Guarantees:
        - Strict tenant isolation (anti-enumeration 404 for wrong company)
        - Database row-level lock (with_for_update)
        - Campaign must be in SCHEDULED state
        - Read-only preflight evaluation (must be eligible)
        - Atomically transitions SCHEDULED -> QUEUED via centralized state machine
        - Enqueues Celery delivery task (primitive IDs only)
        - Broker failure recovery reverts state to SCHEDULED
        """
        stmt = (
            select(Campaign)
            .where(
                Campaign.id == campaign_id,
                Campaign.company_id == company_id,
            )
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found.",
            )

        if campaign.status != CampaignStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot dispatch campaign with status '{campaign.status}'. Only SCHEDULED campaigns can be dispatched by scheduler.",
            )

        # Preflight evaluation for system-driven dispatch (no user context required)
        preflight = await CampaignPreflightService.validate_campaign(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            current_user=None,
            user_role=None,
        )

        if not preflight.eligible:
            blocking_reasons = [issue.message for issue in preflight.issues if issue.blocking]
            reason_str = "; ".join(blocking_reasons) if blocking_reasons else "Campaign is not eligible for execution."
            logger.warning("Preflight failed for scheduled campaign %d: %s", campaign_id, reason_str)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Campaign preflight validation failed: {reason_str}",
            )

        prev_status = campaign.status

        # Mark pre-suppressed recipients as SUPPRESSED upon dispatch
        recip_stmt = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.status == CampaignRecipientStatus.PENDING.value,
        )
        recip_res = await db.execute(recip_stmt)
        pending_recips = list(recip_res.scalars().all())
        if pending_recips:
            emails = {r.email for r in pending_recips}
            suppressed_emails = await SuppressionService.get_suppressed_emails(
                db=db,
                company_id=company_id,
                emails=emails,
            )
            for r in pending_recips:
                if r.email.strip().lower() in suppressed_emails:
                    r.status = CampaignRecipientStatus.SUPPRESSED.value

        # Transition SCHEDULED -> QUEUED via centralized state machine
        campaign = await CampaignService.transition_state(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            target_status=CampaignStatus.QUEUED,
        )

        task_id: Optional[str] = None
        try:
            task = dispatch_campaign_task.delay(
                campaign_id=campaign.id,
                company_id=campaign.company_id,
            )
            if task and hasattr(task, "id"):
                task_id = str(task.id)
            logger.info(
                "Dispatched scheduled campaign %d for company %d (Celery task_id: %s)",
                campaign.id,
                campaign.company_id,
                task_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to enqueue Celery task for scheduled campaign %d: %s. Reverting state to %s.",
                campaign.id,
                exc,
                prev_status,
            )
            campaign.status = prev_status
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to enqueue background dispatch task. Campaign returned to previous state.",
            )

        dispatched_at = datetime.now(timezone.utc)

        return CampaignDispatchResponse(
            campaign_id=campaign.id,
            company_id=campaign.company_id,
            status=CampaignStatus.QUEUED,
            task_id=task_id,
            dispatched_at=dispatched_at,
            eligible_recipient_count=preflight.eligible_recipient_count,
            total_recipient_count=preflight.recipient_count,
        )

