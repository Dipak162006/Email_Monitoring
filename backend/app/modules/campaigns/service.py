from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.sanitizer import sanitize_html
from app.core.storage import AttachmentStorageService
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.campaigns.models import (
    Campaign,
    CampaignAttachment,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    CampaignStep,
    CampaignStatus,
    SuppressionEntry,
)
from app.modules.campaigns.schemas import (
    CampaignAnalyticsResponse,
    CampaignAttachmentRead,
    CampaignCreate,
    CampaignDeliveryTrendPoint,
    CampaignDetailRead,
    CampaignStepAnalytics,
    CampaignStepRead,
    CampaignUpdate,
    CampaignEmailsDrilldownResponse,
)
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.models import Email, EmailDirection, EmailThread
from app.modules.emails.thread_service import EmailThreadService


# Backend-owned campaign lifecycle state machine transition graph
VALID_TRANSITIONS: dict[str, Set[str]] = {
    CampaignStatus.DRAFT.value: {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.QUEUED.value,
        CampaignStatus.ARCHIVED.value,
    },
    CampaignStatus.SCHEDULED.value: {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.QUEUED.value,
        CampaignStatus.DRAFT.value,
        CampaignStatus.CANCELLED.value,
    },
    CampaignStatus.QUEUED.value: {
        CampaignStatus.RUNNING.value,
        CampaignStatus.CANCELLED.value,
        CampaignStatus.FAILED.value,
    },
    CampaignStatus.RUNNING.value: {
        CampaignStatus.PAUSED.value,
        CampaignStatus.CANCELLED.value,
        CampaignStatus.COMPLETED.value,
        CampaignStatus.FAILED.value,
    },
    CampaignStatus.PAUSED.value: {
        CampaignStatus.RUNNING.value,
        CampaignStatus.CANCELLED.value,
    },
    CampaignStatus.COMPLETED.value: {
        CampaignStatus.ARCHIVED.value,
    },
    CampaignStatus.CANCELLED.value: {
        CampaignStatus.ARCHIVED.value,
    },
    CampaignStatus.FAILED.value: {
        CampaignStatus.ARCHIVED.value,
    },
    CampaignStatus.ARCHIVED.value: {
        CampaignStatus.DRAFT.value,
        CampaignStatus.COMPLETED.value,
        CampaignStatus.CANCELLED.value,
    },
}

TERMINAL_STATES: Set[str] = {
    CampaignStatus.COMPLETED.value,
    CampaignStatus.CANCELLED.value,
    CampaignStatus.FAILED.value,
}

ARCHIVABLE_STATES: Set[str] = {
    CampaignStatus.DRAFT.value,
    CampaignStatus.COMPLETED.value,
    CampaignStatus.CANCELLED.value,
    CampaignStatus.FAILED.value,
}

DELETABLE_STATES: Set[str] = {
    CampaignStatus.DRAFT.value,
    CampaignStatus.COMPLETED.value,
    CampaignStatus.CANCELLED.value,
    CampaignStatus.FAILED.value,
    CampaignStatus.ARCHIVED.value,
}


class CampaignService:
    """Service layer managing campaign business logic, tenant isolation, and lifecycle state machine."""

    @staticmethod
    async def get_email_account_for_company(
        db: AsyncSession,
        company_id: int,
        email_account_id: int,
    ) -> EmailAccount:
        """Validate that the designated EmailAccount exists, belongs to the company, and is active."""
        result = await db.execute(
            select(EmailAccount).where(
                EmailAccount.id == email_account_id,
                EmailAccount.company_id == company_id,
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found or does not belong to this company.",
            )
        if not account.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email account is inactive and cannot be used for campaigns.",
            )
        return account

    @staticmethod
    async def create_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_in: CampaignCreate,
        creator_user_id: int,
    ) -> Campaign:
        """Create a new campaign in DRAFT state.
        
        Requires OWNER or ADMIN privileges.
        Validates company ownership and active state of the sender EmailAccount.
        Automatically instantiates Step 1 for the campaign sequence.
        """
        # Validate sender email account
        await CampaignService.get_email_account_for_company(
            db=db,
            company_id=company_id,
            email_account_id=campaign_in.email_account_id,
        )

        now_utc = datetime.now(timezone.utc)
        initial_status = CampaignStatus.DRAFT.value
        validated_scheduled_at = None

        if campaign_in.scheduled_at is not None:
            target_time = (
                campaign_in.scheduled_at
                if campaign_in.scheduled_at.tzinfo
                else campaign_in.scheduled_at.replace(tzinfo=timezone.utc)
            )
            if target_time <= now_utc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scheduled_at must be in the future.",
                )
            validated_scheduled_at = target_time
            initial_status = CampaignStatus.SCHEDULED.value

        campaign = Campaign(
            company_id=company_id,
            email_account_id=campaign_in.email_account_id,
            name=campaign_in.name,
            subject=campaign_in.subject,
            body_text=campaign_in.body_text,
            body_html=campaign_in.body_html,
            scheduled_at=validated_scheduled_at,
            send_interval_seconds=campaign_in.send_interval_seconds,
            status=initial_status,
            created_by_user_id=creator_user_id,
            sending_window=campaign_in.sending_window.model_dump() if campaign_in.sending_window else None,
        )
        db.add(campaign)
        await db.flush()

        # Create authoritative Step 1 for the campaign sequence
        step_1 = CampaignStep(
            campaign_id=campaign.id,
            step_number=1,
            delay_hours=0,
            subject=campaign.subject or "Campaign Step 1",
            body_text=campaign.body_text,
            body_html=campaign.body_html,
            is_active=True,
        )
        db.add(step_1)

        # Synchronize follow-up steps (steps >= 2) if provided
        if campaign_in.followup_steps:
            for idx, f_step in enumerate(campaign_in.followup_steps, start=2):
                subj = (f_step.subject or "").strip()
                if not subj or (subj.startswith("Re: ") and "@" in subj and "@" not in (campaign.subject or "")):
                    subj = ""
                step_item = CampaignStep(
                    campaign_id=campaign.id,
                    step_number=idx,
                    delay_hours=f_step.delay_hours,
                    subject=subj,
                    body_text=f_step.body_text,
                    body_html=f_step.body_html,
                    target_tags=f_step.target_tags or [],
                    is_active=f_step.is_active,
                )
                db.add(step_item)

        campaign_id = campaign.id
        await db.commit()
        return await CampaignService.get_campaign(db, company_id, campaign_id)

    @staticmethod
    async def get_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Retrieve a specific campaign with strict company tenant isolation.
        
        Returns 404 if campaign does not exist or belongs to another company (anti-enumeration).
        """
        result = await db.execute(
            select(Campaign)
            .options(
                selectinload(Campaign.email_account),
                selectinload(Campaign.attachments),
                selectinload(Campaign.steps),
            )
            .where(
                Campaign.id == campaign_id,
                Campaign.company_id == company_id,
            )
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found.",
            )
        return campaign

    @staticmethod
    async def list_campaigns(
        db: AsyncSession,
        company_id: int,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Campaign]:
        """List campaigns belonging to the specified company with stable sorting and pagination.
        
        Includes recipient_count via indexed count subquery without loading heavy recipient models.
        """
        recipient_count_subq = (
            select(func.count(CampaignRecipient.id))
            .where(CampaignRecipient.campaign_id == Campaign.id)
            .correlate(Campaign)
            .scalar_subquery()
        )

        query = (
            select(Campaign, recipient_count_subq.label("recipient_count"))
            .options(
                selectinload(Campaign.attachments),
                selectinload(Campaign.steps),
            )
            .where(Campaign.company_id == company_id)
        )

        if status_filter:
            norm_status = status_filter.strip().upper()
            if norm_status != "ALL":
                query = query.where(Campaign.status == norm_status)
            else:
                query = query.where(Campaign.status != CampaignStatus.ARCHIVED.value)
        else:
            query = query.where(Campaign.status != CampaignStatus.ARCHIVED.value)

        query = query.order_by(Campaign.created_at.desc(), Campaign.id.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        rows = result.all()
        campaigns: List[Campaign] = []
        for campaign, count in rows:
            campaign.recipient_count = count or 0
            campaigns.append(campaign)
        return campaigns

    @staticmethod
    async def get_campaigns_summary(
        db: AsyncSession,
        company_id: int,
    ) -> Dict[str, int]:
        """Aggregate company-wide campaign counts grouped by status for KPI summary cards."""
        stmt = (
            select(Campaign.status, func.count(Campaign.id))
            .where(
                Campaign.company_id == company_id,
                Campaign.status != CampaignStatus.ARCHIVED.value,
            )
            .group_by(Campaign.status)
        )
        res = await db.execute(stmt)
        status_map = dict(res.all())
        active_count = status_map.get(CampaignStatus.RUNNING.value, 0) + status_map.get(CampaignStatus.QUEUED.value, 0)
        scheduled_count = status_map.get(CampaignStatus.SCHEDULED.value, 0)
        draft_count = status_map.get(CampaignStatus.DRAFT.value, 0)
        completed_count = status_map.get(CampaignStatus.COMPLETED.value, 0)
        total_count = sum(status_map.values())
        return {
            "total_count": total_count,
            "active_count": active_count,
            "scheduled_count": scheduled_count,
            "draft_count": draft_count,
            "completed_count": completed_count,
        }

    @staticmethod
    async def update_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        campaign_update: CampaignUpdate,
    ) -> Campaign:
        """Update campaign configuration fields.
        
        Only campaigns in DRAFT or SCHEDULED status may be modified.
        If email_account_id is changed, validates company ownership and active state.
        Direct updates to status or lifecycle timestamps are rejected.
        """
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

        if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit campaign with status '{campaign.status}'. Only DRAFT or SCHEDULED campaigns can be edited.",
            )

        update_data = campaign_update.model_dump(exclude_unset=True)
        followup_steps_in = update_data.pop("followup_steps", None)
        has_followup_update = "followup_steps" in campaign_update.model_fields_set

        if "email_account_id" in update_data and update_data["email_account_id"] is not None:
            await CampaignService.get_email_account_for_company(
                db=db,
                company_id=company_id,
                email_account_id=update_data["email_account_id"],
            )

        # Handle scheduled_at and status transition
        if "scheduled_at" in update_data:
            sched_val = update_data.pop("scheduled_at")
            if sched_val is not None:
                now_utc = datetime.now(timezone.utc)
                target_time = sched_val if sched_val.tzinfo else sched_val.replace(tzinfo=timezone.utc)
                if target_time <= now_utc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="scheduled_at must be in the future.",
                    )
                campaign.scheduled_at = target_time
                campaign.status = CampaignStatus.SCHEDULED.value
                campaign.next_send_at = None
                campaign.started_at = None
                campaign.completed_at = None
            else:
                campaign.scheduled_at = None
                if campaign.status == CampaignStatus.SCHEDULED.value:
                    campaign.status = CampaignStatus.DRAFT.value

        for field, value in update_data.items():
            setattr(campaign, field, value)

        # Synchronize authoritative Step 1 if content fields are updated
        if any(k in update_data for k in ("subject", "body_text", "body_html")):
            step_stmt = select(CampaignStep).where(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.step_number == 1,
            )
            step_1 = (await db.execute(step_stmt)).scalar_one_or_none()
            if step_1:
                if "subject" in update_data and update_data["subject"] is not None:
                    step_1.subject = update_data["subject"]
                elif campaign.subject and not step_1.subject:
                    step_1.subject = campaign.subject
                if "body_text" in update_data:
                    step_1.body_text = update_data["body_text"]
                elif campaign.body_text is not None and step_1.body_text is None:
                    step_1.body_text = campaign.body_text
                if "body_html" in update_data:
                    step_1.body_html = update_data["body_html"]
                elif campaign.body_html is not None and step_1.body_html is None:
                    step_1.body_html = campaign.body_html
            else:
                new_step_1 = CampaignStep(
                    campaign_id=campaign.id,
                    step_number=1,
                    delay_hours=0,
                    subject=campaign.subject or "Campaign Step 1",
                    body_text=campaign.body_text,
                    body_html=campaign.body_html,
                    is_active=True,
                )
                db.add(new_step_1)

        # Synchronize follow-up steps (steps >= 2) if updated
        if has_followup_update:
            from sqlalchemy import delete
            await db.execute(
                delete(CampaignStep).where(
                    CampaignStep.campaign_id == campaign.id,
                    CampaignStep.step_number >= 2,
                )
            )
            if followup_steps_in:
                for idx, f_step in enumerate(followup_steps_in, start=2):
                    subj = (f_step.get("subject") or "").strip()
                    if not subj or (subj.startswith("Re: ") and "@" in subj and "@" not in (campaign.subject or "")):
                        subj = ""
                    step_item = CampaignStep(
                        campaign_id=campaign.id,
                        step_number=idx,
                        delay_hours=f_step.get("delay_hours", 72),
                        subject=subj,
                        body_text=f_step.get("body_text"),
                        body_html=f_step.get("body_html"),
                        target_tags=f_step.get("target_tags") or [],
                        is_active=f_step.get("is_active", True),
                    )
                    db.add(step_item)

        campaign_id = campaign.id
        await db.commit()
        db.expire(campaign, ["steps"])
        return await CampaignService.get_campaign(db, company_id, campaign_id)

    @staticmethod
    async def delete_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> None:
        """Delete an eligible campaign and its associated records via database cascade.
        
        Only campaigns in safe states (DRAFT, COMPLETED, CANCELLED, FAILED) can be deleted.
        Attempts to delete active campaigns (RUNNING, QUEUED, PAUSED) return 409 Conflict.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status not in DELETABLE_STATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete campaign in '{campaign.status}' status. Active campaigns must be completed or cancelled first.",
            )

        await db.delete(campaign)
        await db.commit()

    @staticmethod
    async def transition_state(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        target_status: CampaignStatus,
    ) -> Campaign:
        """Centralized state machine transition mechanism.
        
        Validates transition legality, updates status, sets relevant lifecycle timestamps,
        and atomically persists the change.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        current_status = campaign.status
        target_value = target_status.value

        # Validate against transition graph
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state transition from '{current_status}' to '{target_value}'.",
            )

        # Apply timestamp rules
        now_utc = datetime.now(timezone.utc)
        if target_value == CampaignStatus.RUNNING.value:
            if not campaign.started_at:
                campaign.started_at = now_utc
        elif target_value == CampaignStatus.COMPLETED.value:
            campaign.completed_at = now_utc
            campaign.next_send_at = None
        elif target_value in (CampaignStatus.CANCELLED.value, CampaignStatus.FAILED.value):
            campaign.next_send_at = None
        elif target_value == CampaignStatus.DRAFT.value:
            # Reverting from SCHEDULED to DRAFT clears scheduled_at
            campaign.scheduled_at = None
            campaign.next_send_at = None

        campaign.status = target_value
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def schedule_or_send_now(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        scheduled_at: Optional[datetime] = None,
    ) -> Campaign:
        """Schedule a campaign for future execution, reschedule an existing scheduled campaign, or queue for immediate launch.
        
        Requires campaign to be in DRAFT (for scheduling or send-now) or SCHEDULED (for rescheduling).
        Uses row-level locking (with_for_update) to prevent concurrency races with the background scheduler.
        Sender email account must belong to the company and be active.
        Persists campaign state only (no Celery task dispatching or sending).
        """
        # Tenant-isolated campaign retrieval under row-level lock
        # with_for_update prevents concurrent requests and race conditions with background scheduler
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

        if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot schedule campaign with status '{campaign.status}'. Only DRAFT or SCHEDULED campaigns can be scheduled.",
            )

        # Validate sender account is active and owned
        await CampaignService.get_email_account_for_company(
            db=db,
            company_id=company_id,
            email_account_id=campaign.email_account_id,
        )

        now_utc = datetime.now(timezone.utc)

        if scheduled_at is not None:
            # Validate future datetime
            target_time = scheduled_at if scheduled_at.tzinfo else scheduled_at.replace(tzinfo=timezone.utc)
            if target_time <= now_utc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scheduled_at must be in the future.",
                )
            campaign.scheduled_at = target_time
            campaign.status = CampaignStatus.SCHEDULED.value
            campaign.next_send_at = None
            campaign.started_at = None
            campaign.completed_at = None
        else:
            # If already in SCHEDULED, scheduled_at cannot be omitted to reschedule
            if campaign.status == CampaignStatus.SCHEDULED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scheduled_at must be provided to reschedule an already scheduled campaign.",
                )
            # Immediate send-now -> QUEUED (only allowed from DRAFT)
            campaign.scheduled_at = None
            campaign.status = CampaignStatus.QUEUED.value

        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def pause_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Pause an actively executing (RUNNING) campaign.
        
        Transition: RUNNING -> PAUSED.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status != CampaignStatus.RUNNING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot pause campaign with status '{campaign.status}'. Only RUNNING campaigns can be paused.",
            )
        return await CampaignService.transition_state(db, company_id, campaign_id, CampaignStatus.PAUSED)

    @staticmethod
    async def resume_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Resume a previously paused campaign.
        
        Transition: PAUSED -> RUNNING.
        Resumes delivery execution via Celery background delivery task.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status != CampaignStatus.PAUSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resume campaign with status '{campaign.status}'. Only PAUSED campaigns can be resumed.",
            )

        # Transition PAUSED -> RUNNING via centralized state machine
        campaign = await CampaignService.transition_state(db, company_id, campaign_id, CampaignStatus.RUNNING)

        # Check if an actual C8 campaign execution worker is actively mid-send.
        # This distinguishes active C8 campaign execution from C9 retry workers
        # (which also set delivery status = SENDING for retries of failed recipients).
        from app.modules.campaigns.delivery_service import CampaignDeliveryService

        is_worker_active = await CampaignDeliveryService.has_active_campaign_worker(db, campaign_id)

        # If no C8 campaign worker is currently mid-send, enqueue delivery task to continue remaining recipients
        if not is_worker_active:
            try:
                from app.workers.campaign_tasks import dispatch_campaign_task
                now_utc = datetime.now(timezone.utc)
                if campaign.send_interval_seconds > 0 and campaign.next_send_at and campaign.next_send_at > now_utc:
                    delay = max(1, int((campaign.next_send_at - now_utc).total_seconds()))
                    dispatch_campaign_task.apply_async(
                        args=[campaign.id, campaign.company_id],
                        countdown=delay,
                    )
                else:
                    if campaign.send_interval_seconds > 0:
                        campaign.next_send_at = now_utc
                        await db.commit()
                        await db.refresh(campaign)
                    dispatch_campaign_task.delay(
                        campaign_id=campaign.id,
                        company_id=campaign.company_id,
                    )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Could not enqueue Celery task on resume for campaign %d: %s", campaign.id, exc
                )

        return campaign

    @staticmethod
    async def cancel_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Cancel an eligible campaign.
        
        Transitions: SCHEDULED, QUEUED, RUNNING, PAUSED -> CANCELLED.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        cancellable = {
            CampaignStatus.SCHEDULED.value,
            CampaignStatus.QUEUED.value,
            CampaignStatus.RUNNING.value,
            CampaignStatus.PAUSED.value,
        }
        if campaign.status not in cancellable:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel campaign with status '{campaign.status}'. Only SCHEDULED, QUEUED, RUNNING, or PAUSED campaigns can be cancelled.",
            )
        campaign = await CampaignService.transition_state(db, company_id, campaign_id, CampaignStatus.CANCELLED)
        
        # Safely transition any pending/active/sent recipients to STOPPED and clear pending follow-ups
        recip_stmt = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.status.in_([
                CampaignRecipientStatus.ACTIVE.value,
                CampaignRecipientStatus.PENDING.value,
                CampaignRecipientStatus.SENT.value,
            ]),
        )
        recips_res = await db.execute(recip_stmt)
        for recip in recips_res.scalars().all():
            recip.next_step_due_at = None
            if recip.status != CampaignRecipientStatus.COMPLETED.value:
                recip.status = CampaignRecipientStatus.STOPPED.value
                recip.stopped_reason = CampaignRecipientStopReason.CAMPAIGN_CANCELLED.value

        await db.commit()
        return campaign

    @staticmethod
    async def archive_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Archive an eligible campaign (DRAFT, COMPLETED, CANCELLED, FAILED).
        
        Active campaigns (RUNNING, QUEUED, SCHEDULED, PAUSED) cannot be archived directly and return 409 Conflict.
        Clears next_send_at and preserves all recipients, steps, and delivery history.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status == CampaignStatus.ARCHIVED.value:
            return campaign

        if campaign.status not in ARCHIVABLE_STATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot archive campaign in '{campaign.status}' status. Active campaigns must be completed or cancelled first.",
            )

        campaign.status = CampaignStatus.ARCHIVED.value
        campaign.next_send_at = None
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def restore_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Restore an archived campaign safely to its non-active resting state.
        
        Restores to:
        - COMPLETED if completed_at was set
        - DRAFT if started_at is None (unstarted draft)
        - CANCELLED if started_at is set but incomplete
        
        Never automatically resumes or schedules delivery.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status != CampaignStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot restore campaign with status '{campaign.status}'. Only ARCHIVED campaigns can be restored.",
            )

        if campaign.completed_at is not None:
            campaign.status = CampaignStatus.COMPLETED.value
        elif campaign.started_at is None:
            campaign.status = CampaignStatus.DRAFT.value
        else:
            campaign.status = CampaignStatus.CANCELLED.value

        campaign.next_send_at = None
        await db.commit()
        await db.refresh(campaign)
        return campaign

    @staticmethod
    async def get_recipient_count(db: AsyncSession, campaign_id: int) -> int:
        """Count total recipients belonging to a campaign using the indexed campaign_id."""
        result = await db.execute(
            select(func.count(CampaignRecipient.id)).where(
                CampaignRecipient.campaign_id == campaign_id
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_recipient_status_counts(db: AsyncSession, campaign_id: int) -> dict[str, int]:
        """Execute a single indexed query on CampaignRecipient for campaign_id.
        
        Returns a dictionary containing total recipient count and breakdown by status:
        total, pending_count, sent_count, failed_count, bounced_count, suppressed_count,
        active_count, completed_count, stopped_count, uncertain_count.
        """
        stmt = (
            select(
                CampaignRecipient.status,
                CampaignRecipient.stopped_reason,
                CampaignRecipient.current_step_number,
                func.count(CampaignRecipient.id),
            )
            .where(CampaignRecipient.campaign_id == campaign_id)
            .group_by(
                CampaignRecipient.status,
                CampaignRecipient.stopped_reason,
                CampaignRecipient.current_step_number,
            )
        )
        res = await db.execute(stmt)
        rows = res.all()
        counts: dict[str, int] = {
            "total": 0,
            "pending_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "bounced_count": 0,
            "suppressed_count": 0,
            "active_count": 0,
            "completed_count": 0,
            "stopped_count": 0,
            "uncertain_count": 0,
        }
        for status_val, stopped_reason, step_num, count_val in rows:
            c = count_val or 0
            counts["total"] += c
            val_str = status_val.value if hasattr(status_val, "value") else str(status_val)

            if val_str == "ACTIVE":
                counts["active_count"] += c
                if step_num == 0:
                    counts["pending_count"] += c
                else:
                    counts["sent_count"] += c
            elif val_str == "COMPLETED":
                counts["completed_count"] += c
                counts["sent_count"] += c
            elif val_str == "STOPPED":
                counts["stopped_count"] += c
                if stopped_reason == "BOUNCED":
                    counts["bounced_count"] += c
                elif stopped_reason in ("UNSUBSCRIBED", "MANUAL"):
                    counts["suppressed_count"] += c
                    if step_num >= 1:
                        counts["sent_count"] += c
                elif stopped_reason == "CAMPAIGN_CANCELLED":
                    counts["failed_count"] += c
                elif stopped_reason == "REPLIED":
                    counts["sent_count"] += c
            else:
                # Legacy fallback
                status_key = f"{val_str.lower()}_count"
                if status_key in counts:
                    counts[status_key] += c

        # Also tally uncertain deliveries if any exist
        deliv_uncertain_stmt = select(func.count(CampaignDelivery.id)).where(
            CampaignDelivery.campaign_id == campaign_id,
            CampaignDelivery.status == CampaignDeliveryStatus.UNCERTAIN.value,
        )
        uncertain_c = await db.scalar(deliv_uncertain_stmt) or 0
        counts["uncertain_count"] = uncertain_c

        # Follow-up sequence telemetry counters
        # Verified replies: verified thread_has_reply, matching inbound email, or non-disproven stopped reply
        from email.utils import parseaddr
        from app.modules.emails.models import Email, EmailDirection, EmailThread
        from app.modules.emails.thread_service import EmailThreadService

        deliv_stmt = (
            select(
                CampaignDelivery.recipient_id,
                CampaignDelivery.message_id,
                CampaignDelivery.thread_id,
                EmailThread.has_reply,
            )
            .outerjoin(EmailThread, CampaignDelivery.thread_id == EmailThread.id)
            .where(CampaignDelivery.campaign_id == campaign_id)
        )
        deliv_rows = (await db.execute(deliv_stmt)).all()

        matched_reply_recip_ids: set[int] = set()
        deliv_by_msg_id: dict[str, int] = {}
        recip_deliv_threads: dict[int, list[tuple[Optional[int], Optional[bool]]]] = {}

        for r_id, msg_id, th_id, th_reply in deliv_rows:
            # NOTE: th_reply (thread.has_reply) is NOT used here because it can be
            # True due to outbound emails being imported back into the thread.
            # Replies are only counted via verified inbound email header matching below.
            if msg_id:
                clean_mid = msg_id.strip()
                deliv_by_msg_id[clean_mid] = r_id
                stripped_mid = clean_mid.strip("<>")
                deliv_by_msg_id[stripped_mid] = r_id
                deliv_by_msg_id[f"<{stripped_mid}>"] = r_id
            if r_id not in recip_deliv_threads:
                recip_deliv_threads[r_id] = []
            recip_deliv_threads[r_id].append((th_id, th_reply))

        if deliv_by_msg_id:
            camp_stmt = select(Campaign.company_id, Campaign.email_account_id).where(Campaign.id == campaign_id)
            camp_row = (await db.execute(camp_stmt)).first()
            if camp_row:
                comp_id, camp_acc_id = camp_row[0], camp_row[1]
                camp_sender_email = ""
                if camp_acc_id:
                    acc_email = await db.scalar(
                        select(EmailAccount.email_address).where(EmailAccount.id == camp_acc_id)
                    )
                    if acc_email:
                        camp_sender_email = acc_email.strip().lower()

                recip_emails = dict((await db.execute(
                    select(CampaignRecipient.id, CampaignRecipient.email)
                    .where(CampaignRecipient.campaign_id == campaign_id)
                )).all())

                inc_emails = (await db.execute(
                    select(Email.in_reply_to, Email.references_header, Email.sender)
                    .where(
                        Email.company_id == comp_id,
                        Email.direction == EmailDirection.INCOMING.value,
                    )
                )).all()

                for in_reply, refs, sender in inc_emails:
                    sender_clean = parseaddr(sender)[1].strip().lower() if sender else ""
                    if not sender_clean or (camp_sender_email and sender_clean == camp_sender_email):
                        continue

                    candidate_cids = []
                    if in_reply:
                        candidate_cids.extend(EmailThreadService.extract_message_ids(in_reply))
                        clean_in_reply = in_reply.strip()
                        if clean_in_reply not in candidate_cids:
                            candidate_cids.append(clean_in_reply)
                    if refs:
                        candidate_cids.extend(EmailThreadService.extract_message_ids(refs))

                    for cid in candidate_cids:
                        cid_clean = cid.strip()
                        target_r_id = deliv_by_msg_id.get(cid_clean)
                        if target_r_id and (recip_emails.get(target_r_id) or "").strip().lower() == sender_clean:
                            matched_reply_recip_ids.add(target_r_id)
                            break

        # Fallback attribution via stopped_reason='REPLIED' or replied_at has been
        # removed. Only header-verified inbound email matches count as genuine replies.
        # This prevents stale/incorrect recipient state from inflating reply counts.

        counts["replied_count"] = len(matched_reply_recip_ids)
        counts["unique_replied_count"] = len(matched_reply_recip_ids)

        followup_sched_stmt = select(func.count(CampaignRecipient.id)).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.next_step_due_at.is_not(None),
            CampaignRecipient.stopped_reason.is_(None),
        )
        counts["followup_scheduled_count"] = (await db.scalar(followup_sched_stmt)) or 0

        initial_sent_stmt = (
            select(func.count(CampaignDelivery.id))
            .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
            .where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.status == CampaignDeliveryStatus.SENT.value,
                CampaignStep.step_number == 1,
            )
        )
        initial_sent = (await db.scalar(initial_sent_stmt)) or 0
        counts["initial_sent_count"] = initial_sent

        followup_sent_stmt = (
            select(func.count(CampaignDelivery.id))
            .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
            .where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.status == CampaignDeliveryStatus.SENT.value,
                CampaignStep.step_number >= 2,
            )
        )
        followup_sent = (await db.scalar(followup_sent_stmt)) or 0
        counts["followup_sent_count"] = followup_sent
        counts["total_sent_count"] = initial_sent + followup_sent
        # Authoritative Step 1 sends: preserve historical Initial Sent even if recipients were later stopped
        counts["sent_count"] = initial_sent if initial_sent > 0 else counts["sent_count"]

        return counts

    @staticmethod
    def to_detail_schema(
        campaign: Campaign,
        recipient_count: Optional[int] = None,
        status_counts: Optional[dict[str, int]] = None,
    ) -> CampaignDetailRead:
        """Convert a Campaign model instance into a CampaignDetailRead schema."""
        email_account = campaign.__dict__.get("email_account")
        recipients = campaign.__dict__.get("recipients")
        attachments = campaign.__dict__.get("attachments") or []
        steps_models = campaign.__dict__.get("steps")
        if steps_models is None:
            steps_models = getattr(campaign, "steps", None) or []

        counts = status_counts or {}
        final_count = (
            recipient_count
            if recipient_count is not None
            else counts.get("total", len(recipients) if recipients is not None else 0)
        )

        sorted_steps = sorted(steps_models, key=lambda s: s.step_number)
        step_1_model = next((s for s in sorted_steps if s.step_number == 1), None)

        effective_subject = campaign.subject or (step_1_model.subject if step_1_model else "")
        effective_body_text = campaign.body_text or (step_1_model.body_text if step_1_model else None)
        effective_body_html = campaign.body_html or (step_1_model.body_html if step_1_model else None)

        steps_read = []
        for s in sorted_steps:
            sr = CampaignStepRead.model_validate(s)
            if sr.step_number == 1:
                sr = sr.model_copy(
                    update={
                        "subject": effective_subject or sr.subject,
                        "body_text": effective_body_text if effective_body_text is not None else sr.body_text,
                        "body_html": effective_body_html if effective_body_html is not None else sr.body_html,
                    }
                )
            elif sr.step_number >= 2:
                resolved_subj = sr.subject
                if not resolved_subj or resolved_subj == "Follow-up" or (resolved_subj.startswith("Re: ") and ("@" in resolved_subj and "@" not in effective_subject)):
                    resolved_subj = f"Re: {effective_subject}"[:255] if effective_subject else "Follow-up"
                sr = sr.model_copy(update={"subject": resolved_subj})
            steps_read.append(sr)

        followup_steps_read = [s for s in steps_read if s.step_number >= 2]

        return CampaignDetailRead(
            id=campaign.id,
            company_id=campaign.company_id,
            email_account_id=campaign.email_account_id,
            name=campaign.name,
            subject=effective_subject,
            body_text=effective_body_text,
            body_html=effective_body_html,
            status=campaign.status,
            scheduled_at=campaign.scheduled_at,
            started_at=campaign.started_at,
            completed_at=campaign.completed_at,
            send_interval_seconds=campaign.send_interval_seconds if campaign.send_interval_seconds is not None else 0,
            next_send_at=campaign.next_send_at,
            created_by_user_id=campaign.created_by_user_id,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
            email_account_name=email_account.name if email_account else None,
            email_account_address=email_account.email_address if email_account else None,
            recipient_count=final_count,
            pending_count=counts.get("pending_count", 0),
            sent_count=counts.get("sent_count", 0),
            failed_count=counts.get("failed_count", 0),
            bounced_count=counts.get("bounced_count", 0),
            suppressed_count=counts.get("suppressed_count", 0),
            replied_count=counts.get("replied_count", 0),
            followup_scheduled_count=counts.get("followup_scheduled_count", 0),
            followup_sent_count=counts.get("followup_sent_count", 0),
            initial_sent_count=counts.get("initial_sent_count", 0),
            total_sent_count=counts.get("total_sent_count", 0),
            unique_replied_count=counts.get("unique_replied_count", counts.get("replied_count", 0)),
            attachments=[CampaignAttachmentRead.model_validate(a) for a in attachments],
            steps=steps_read,
            followup_steps=followup_steps_read,
            sending_window=getattr(campaign, "sending_window", None),
        )

    @staticmethod
    async def upload_attachment(
        db: AsyncSession,
        current_user: User,
        company_id: int,
        campaign_id: int,
        upload_file: UploadFile,
    ) -> CampaignAttachment:
        """Upload and associate an attachment with an editable draft campaign.
        
        Validates:
        - Campaign exists and belongs to company.
        - Campaign is in DRAFT status.
        - Total campaign attachments limit (max 10).
        - Secure file upload and size limit (<= 25 MB) via AttachmentStorageService.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status != CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add attachments to campaign with status '{campaign.status}'. Only DRAFT campaigns support adding attachments.",
            )

        existing_count_stmt = select(func.count(CampaignAttachment.id)).where(
            CampaignAttachment.campaign_id == campaign_id
        )
        existing_count = (await db.execute(existing_count_stmt)).scalar() or 0
        if existing_count >= 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum of 10 attachments allowed per campaign.",
            )

        try:
            safe_name, content_type, file_size, rel_path = await AttachmentStorageService.save_upload_file(
                company_id=campaign.company_id,
                account_id=campaign.email_account_id,
                upload_file=upload_file,
            )
        except ValueError as e:
            err_msg = str(e)
            if "exceeds maximum limit" in err_msg:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=err_msg,
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )

        attachment = CampaignAttachment(
            campaign_id=campaign.id,
            company_id=campaign.company_id,
            email_account_id=campaign.email_account_id,
            file_name=safe_name,
            content_type=content_type,
            file_size=file_size,
            storage_path=rel_path,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        return attachment

    @staticmethod
    async def list_attachments(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> List[CampaignAttachment]:
        """List all attachments associated with a campaign."""
        await CampaignService.get_campaign(db, company_id, campaign_id)
        stmt = (
            select(CampaignAttachment)
            .where(CampaignAttachment.campaign_id == campaign_id)
            .order_by(CampaignAttachment.id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def delete_attachment(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        attachment_id: int,
    ) -> None:
        """Delete an attachment from an editable draft campaign and safely clean up disk storage."""
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status != CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot remove attachments from campaign with status '{campaign.status}'. Only DRAFT campaigns support removing attachments.",
            )

        from app.modules.emails.models import EmailAttachment
        att_stmt = select(CampaignAttachment).where(
            CampaignAttachment.id == attachment_id,
            CampaignAttachment.campaign_id == campaign_id,
            CampaignAttachment.company_id == company_id,
        )
        res = await db.execute(att_stmt)
        attachment = res.scalar_one_or_none()
        if not attachment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found.",
            )

        storage_path = attachment.storage_path
        await db.delete(attachment)
        await db.commit()

        # Check if physical file is referenced by any other EmailAttachment or CampaignAttachment
        ref_stmt1 = select(func.count(EmailAttachment.id)).where(EmailAttachment.storage_path == storage_path)
        ref_stmt2 = select(func.count(CampaignAttachment.id)).where(CampaignAttachment.storage_path == storage_path)
        refs1 = (await db.execute(ref_stmt1)).scalar() or 0
        refs2 = (await db.execute(ref_stmt2)).scalar() or 0
        if refs1 + refs2 == 0:
            await AttachmentStorageService.delete_file(storage_path)

    @staticmethod
    async def get_attachment_for_download(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        attachment_id: int,
    ) -> Tuple[Path, str, str]:
        """Verify access and return resolved physical file path, filename, and content type."""
        await CampaignService.get_campaign(db, company_id, campaign_id)
        att_stmt = select(CampaignAttachment).where(
            CampaignAttachment.id == attachment_id,
            CampaignAttachment.campaign_id == campaign_id,
            CampaignAttachment.company_id == company_id,
        )
        res = await db.execute(att_stmt)
        attachment = res.scalar_one_or_none()
        if not attachment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found.",
            )

        try:
            file_path = AttachmentStorageService.resolve_storage_path(attachment.storage_path)
            if not file_path.is_file():
                raise FileNotFoundError()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment content file is missing from storage.",
            )

        return file_path, attachment.file_name, attachment.content_type

    @staticmethod
    async def import_draft(
        db: AsyncSession,
        current_user: User,
        company_id: int,
        campaign_id: int,
        draft_id: int,
    ) -> Campaign:
        """Import subject, body, and compatible attachments from an authorized draft into a DRAFT campaign.
        
        Guarantees:
        - Draft must belong to the same company and sender EmailAccount.
        - User must have authorized access to the sender EmailAccount.
        - Editing campaign content does not mutate or send the original draft.
        - Compatible draft attachments are copied as CampaignAttachment references pointing to the
          existing storage path (zero redundant file duplication).
        - Missing or corrupt physical attachment files are gracefully ignored.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status != CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot import draft into campaign with status '{campaign.status}'. Only DRAFT campaigns can be modified.",
            )

        from app.modules.emails.models import Email, EmailStatus, EmailAttachment
        draft = await db.get(Email, draft_id)
        if not draft or draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found or belongs to another company.",
            )

        if draft.is_deleted or draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified email is not an active draft.",
            )

        if draft.email_account_id != campaign.email_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Draft belongs to a different sender account than the campaign.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        membership = await CompanyService.get_user_membership(db, company_id, current_user.id)
        if not account or not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this draft.",
            )
        has_access = await EmailAccountService.check_user_access(
            db=db,
            account=account,
            user_id=current_user.id,
            user_role=membership.role,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this draft's email account.",
            )

        # Import content safely
        if draft.subject is not None:
            campaign.subject = draft.subject
        if draft.body_html:
            campaign.body_html = sanitize_html(draft.body_html)
        elif draft.body_html == "":
            campaign.body_html = ""

        if draft.body_text is not None:
            campaign.body_text = draft.body_text

        # Import compatible attachments
        draft_att_stmt = select(EmailAttachment).where(EmailAttachment.email_id == draft_id)
        draft_att_res = await db.execute(draft_att_stmt)
        draft_attachments = draft_att_res.scalars().all()

        for d_att in draft_attachments:
            try:
                disk_path = AttachmentStorageService.resolve_storage_path(d_att.storage_path)
                if not disk_path.is_file():
                    continue
            except Exception:
                continue

            # Check if campaign already has this attachment
            existing_camp_att = await db.execute(
                select(CampaignAttachment).where(
                    CampaignAttachment.campaign_id == campaign_id,
                    CampaignAttachment.storage_path == d_att.storage_path,
                )
            )
            if existing_camp_att.scalar_one_or_none():
                continue

            camp_att = CampaignAttachment(
                campaign_id=campaign_id,
                company_id=company_id,
                email_account_id=campaign.email_account_id,
                file_name=d_att.file_name,
                content_type=d_att.content_type,
                file_size=d_att.file_size,
                storage_path=d_att.storage_path,
            )
            db.add(camp_att)

        # Synchronize Step 1 with imported draft content
        step_stmt = select(CampaignStep).where(
            CampaignStep.campaign_id == campaign.id,
            CampaignStep.step_number == 1,
        )
        step_1 = (await db.execute(step_stmt)).scalar_one_or_none()
        if step_1:
            step_1.subject = campaign.subject or "Campaign Step 1"
            step_1.body_html = campaign.body_html
            step_1.body_text = campaign.body_text
        else:
            new_step_1 = CampaignStep(
                campaign_id=campaign.id,
                step_number=1,
                delay_hours=0,
                subject=campaign.subject or "Campaign Step 1",
                body_text=campaign.body_text,
                body_html=campaign.body_html,
                is_active=True,
            )
            db.add(new_step_1)

        await db.commit()
        await db.refresh(campaign)
        return await CampaignService.get_campaign(db, company_id, campaign_id)

    @staticmethod
    async def get_campaign_analytics(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> CampaignAnalyticsResponse:
        """Calculate step-level analytics funnel from persisted delivery and recipient records.
        
        Strictly enforces company tenant isolation (raises 404 if not found).
        Derives outcomes per step using existing stored data:
        - targeted_count: Step 1 = all recipients; Follow-ups = tag-targeted recipients (or all if untargeted)
        - sent_count: deliveries with status SENT (scoped to targeted recipients)
        - sending_count: deliveries with status SENDING (scoped to targeted recipients)
        - bounced_count: deliveries with status BOUNCED or bounced_at IS NOT NULL
        - failed_count: deliveries with status FAILED (excluding bounced)
        - skipped_count: deliveries with status SKIPPED for targeted recipients
        - replied_count: distinct replying recipients attributed to their single highest sent step (replied_count <= sent_count)
        - pending_count: active recipients queued or progressing towards their next eligible step (at most 1 step per recipient)
        - delivery_rate, reply_rate, bounce_rate with safe zero-division handling
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        # 1. Fetch steps sorted by step_number
        steps_stmt = (
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign.id)
            .order_by(CampaignStep.step_number.asc())
        )
        steps = (await db.execute(steps_stmt)).scalars().all()

        # 2. Fetch all recipients for this campaign
        recip_stmt = (
            select(CampaignRecipient)
            .where(CampaignRecipient.campaign_id == campaign.id)
        )
        recipients = (await db.execute(recip_stmt)).scalars().all()
        total_recipients = len(recipients)

        # 3. Fetch all deliveries and check for thread replies via EmailThread and message_id
        from app.modules.emails.models import EmailThread, Email, EmailDirection
        from app.modules.emails.thread_service import EmailThreadService
        from sqlalchemy import or_

        deliv_stmt = (
            select(
                CampaignDelivery.id,
                CampaignDelivery.step_id,
                CampaignDelivery.recipient_id,
                CampaignDelivery.status,
                CampaignDelivery.sent_at,
                CampaignDelivery.bounced_at,
                CampaignDelivery.thread_id,
                EmailThread.has_reply,
                CampaignDelivery.message_id,
            )
            .outerjoin(EmailThread, CampaignDelivery.thread_id == EmailThread.id)
            .where(CampaignDelivery.campaign_id == campaign.id)
        )
        deliv_rows = (await db.execute(deliv_stmt)).all()

        deliv_by_recipient_step: dict[tuple[int, int], dict] = {}
        deliv_by_step: dict[int, list[dict]] = {s.id: [] for s in steps}
        sent_steps_by_recipient: dict[int, list[dict]] = {r.id: [] for r in recipients}

        for row in deliv_rows:
            d_id, s_id, r_id, status_val, sent_at, bounced_at, thread_id, thread_has_reply, msg_id = row
            deliv_data = {
                "id": d_id,
                "step_id": s_id,
                "recipient_id": r_id,
                "status": status_val,
                "sent_at": sent_at,
                "bounced_at": bounced_at,
                "thread_id": thread_id,
                "thread_has_reply": bool(thread_has_reply),
                "message_id": msg_id,
            }
            deliv_by_recipient_step[(r_id, s_id)] = deliv_data
            if s_id in deliv_by_step:
                deliv_by_step[s_id].append(deliv_data)

            if status_val == CampaignDeliveryStatus.SENT.value:
                step_obj = next((s for s in steps if s.id == s_id), None)
                if step_obj and r_id in sent_steps_by_recipient:
                    sent_steps_by_recipient[r_id].append({
                        "step_number": step_obj.step_number,
                        "step_id": step_obj.id,
                        "sent_at": sent_at,
                        "message_id": msg_id,
                    })

        # Precompute set of targeted recipient IDs per step
        step_targeted_recipient_ids: dict[int, set[int]] = {}
        for step in steps:
            target_tags = step.target_tags or []
            if step.step_number == 1 or not target_tags:
                step_targeted_recipient_ids[step.id] = {r.id for r in recipients}
            else:
                tag_set = {t.strip().lower() for t in target_tags if t and t.strip()}
                step_targeted_recipient_ids[step.id] = {
                    r.id for r in recipients
                    if any(t.strip().lower() in tag_set for t in (r.tags or []))
                }

        # Index deliveries by message_id for fast, reliable header-based reply attribution
        deliv_by_message_id: dict[str, dict] = {}
        for d in deliv_by_recipient_step.values():
            m_id = d.get("message_id")
            if m_id:
                clean_m = m_id.strip()
                deliv_by_message_id[clean_m] = d
                deliv_by_message_id[clean_m.strip("<>")] = d
                deliv_by_message_id[f"<{clean_m.strip('<>')}>"] = d

        # Query all incoming emails associated with this campaign's threads or referencing deliveries
        campaign_thread_ids = {d["thread_id"] for d in deliv_by_recipient_step.values() if d.get("thread_id") is not None}
        campaign_msg_ids = list(deliv_by_message_id.keys())

        inc_conditions = []
        if campaign_thread_ids:
            inc_conditions.append(Email.thread_id.in_(campaign_thread_ids))
        if campaign_msg_ids:
            mids_slice = campaign_msg_ids[:500]
            inc_conditions.append(Email.in_reply_to.in_(mids_slice))
            ref_clauses = [Email.references_header.contains(mid) for mid in mids_slice if len(mid) > 5]
            if ref_clauses:
                inc_conditions.append(or_(*ref_clauses))

        incoming_reply_emails = []
        if inc_conditions:
            inc_stmt = (
                select(
                    Email.id,
                    Email.thread_id,
                    Email.message_id,
                    Email.in_reply_to,
                    Email.references_header,
                    Email.sender,
                    Email.sent_at,
                    Email.received_at,
                )
                .where(
                    Email.company_id == campaign.company_id,
                    Email.direction == EmailDirection.INCOMING.value,
                    or_(*inc_conditions),
                )
            )
            incoming_reply_emails = (await db.execute(inc_stmt)).all()

        # 4. Attribute replies to the exact referenced step using actual message headers & records
        from email.utils import parseaddr
        camp_sender_email = (campaign.email_account.email_address if campaign.email_account else "").strip().lower()

        recipient_replied_steps: dict[int, set[int]] = {r.id: set() for r in recipients}
        matched_reply_recipient_ids: set[int] = set()

        # Step 4a: Primary Attribution via In-Reply-To and References headers
        for inc_row in incoming_reply_emails:
            (
                inc_id,
                inc_thread_id,
                inc_msg_id,
                inc_in_reply_to,
                inc_refs,
                inc_sender,
                inc_sent_at,
                inc_received_at,
            ) = inc_row

            inc_sender_clean = parseaddr(inc_sender)[1].strip().lower() if inc_sender else ""
            if not inc_sender_clean:
                continue
            # Exclude emails originating from the campaign's own sending account
            if camp_sender_email and inc_sender_clean == camp_sender_email:
                continue

            candidate_ids = []
            if inc_in_reply_to:
                candidate_ids.extend(EmailThreadService.extract_message_ids(inc_in_reply_to))
                clean_in_reply = inc_in_reply_to.strip()
                if clean_in_reply not in candidate_ids:
                    candidate_ids.append(clean_in_reply)
            if inc_refs:
                ref_ids = EmailThreadService.extract_message_ids(inc_refs)
                for rid in reversed(ref_ids):
                    if rid not in candidate_ids:
                        candidate_ids.append(rid)

            matched_deliv = None
            for cid in candidate_ids:
                if cid in deliv_by_message_id:
                    matched_deliv = deliv_by_message_id[cid]
                    break
                stripped = cid.strip("<>")
                if stripped in deliv_by_message_id:
                    matched_deliv = deliv_by_message_id[stripped]
                    break
                bracketed = f"<{stripped}>"
                if bracketed in deliv_by_message_id:
                    matched_deliv = deliv_by_message_id[bracketed]
                    break

            if matched_deliv:
                r_id = matched_deliv["recipient_id"]
                recip_obj = next((r for r in recipients if r.id == r_id), None)
                if not recip_obj:
                    continue
                # Only recognize an incoming reply when its sender matches the actual campaign recipient
                recip_email = (recip_obj.email or "").strip().lower()
                if inc_sender_clean != recip_email:
                    continue

                step_obj = next((s for s in steps if s.id == matched_deliv["step_id"]), None)
                if step_obj:
                    recipient_replied_steps[r_id].add(step_obj.step_number)
                    matched_reply_recipient_ids.add(r_id)

        # Step 4b: Fallback Attribution for recipients with verified delivery or thread evidence
        for r in recipients:
            recipient_delivs = [d for d in deliv_by_recipient_step.values() if d.get("recipient_id") == r.id]
            has_thread_reply = any(d.get("thread_has_reply") for d in recipient_delivs)

            has_disproven_thread = bool(recipient_delivs) and all(
                d.get("thread_id") is not None and not d.get("thread_has_reply")
                for d in recipient_delivs
            )

            has_genuine_reply = (
                r.id in matched_reply_recipient_ids
                or has_thread_reply
                or (
                    r.status == CampaignRecipientStatus.STOPPED.value
                    and r.stopped_reason == CampaignRecipientStopReason.REPLIED.value
                    and not has_disproven_thread
                )
            )
            if not has_genuine_reply:
                continue

            matched_reply_recipient_ids.add(r.id)

            # If this recipient already has step attribution via headers, preserve it
            if recipient_replied_steps[r.id]:
                continue

            sent_entries = sent_steps_by_recipient.get(r.id, [])
            if not sent_entries:
                # Do NOT assign unmatched replies to an arbitrary step
                continue

            sorted_sent = sorted(
                sent_entries,
                key=lambda x: (x["sent_at"] or datetime.min.replace(tzinfo=timezone.utc), x["step_number"]),
            )

            target_step_num = None
            if r.replied_at is not None:
                reply_cutoff = r.replied_at + timedelta(seconds=60)
                eligible_entries = [e for e in sorted_sent if e["sent_at"] is None or e["sent_at"] <= reply_cutoff]
                if eligible_entries:
                    target_step_num = eligible_entries[-1]["step_number"]

            if target_step_num is None:
                # If replied_at is missing, attribute to the latest sent step before stopping
                target_step_num = sorted_sent[-1]["step_number"]

            recipient_replied_steps[r.id].add(target_step_num)

        # 5. Determine at most one pending step per active recipient
        recipient_pending_step_id: dict[int, int] = {}
        for r in recipients:
            if r.stopped_reason is not None or r.status in (
                CampaignRecipientStatus.STOPPED.value,
                CampaignRecipientStatus.COMPLETED.value,
            ):
                continue

            # If recipient already has a delivery currently PENDING or SENDING, that is their pending step
            explicit_pending_step_id = None
            for step in steps:
                d = deliv_by_recipient_step.get((r.id, step.id))
                if d and d["status"] in (CampaignDeliveryStatus.PENDING.value, CampaignDeliveryStatus.SENDING.value):
                    explicit_pending_step_id = step.id
                    break

            if explicit_pending_step_id is not None:
                recipient_pending_step_id[r.id] = explicit_pending_step_id
                continue

            # Otherwise, find the first future step that targets this recipient
            for step in steps:
                if step.step_number <= r.current_step_number:
                    continue
                d = deliv_by_recipient_step.get((r.id, step.id))
                if d and d["status"] in (
                    CampaignDeliveryStatus.SENT.value,
                    CampaignDeliveryStatus.BOUNCED.value,
                    CampaignDeliveryStatus.FAILED.value,
                    CampaignDeliveryStatus.SKIPPED.value,
                ):
                    continue

                if r.id in step_targeted_recipient_ids.get(step.id, set()):
                    recipient_pending_step_id[r.id] = step.id
                    break

        # 6. Aggregate per-step metrics
        step_analytics_list: List[CampaignStepAnalytics] = []

        for step in steps:
            targeted_ids = step_targeted_recipient_ids.get(step.id, set())
            targeted_count = len(targeted_ids)
            target_tags = step.target_tags or []

            # Only deliveries of targeted recipients belong to this step's funnel
            step_delivs = [d for d in deliv_by_step.get(step.id, []) if d["recipient_id"] in targeted_ids]
            recipient_ids_with_deliv = {d["recipient_id"] for d in step_delivs}

            sent_count = 0
            sending_count = 0
            bounced_count = 0
            failed_count = 0
            skipped_count = 0

            for d in step_delivs:
                st = d["status"]
                is_bounced = st == CampaignDeliveryStatus.BOUNCED.value or d["bounced_at"] is not None
                if is_bounced:
                    bounced_count += 1
                elif st == CampaignDeliveryStatus.SENT.value:
                    sent_count += 1
                elif st == CampaignDeliveryStatus.SENDING.value:
                    sending_count += 1
                elif st == CampaignDeliveryStatus.FAILED.value:
                    failed_count += 1
                elif st == CampaignDeliveryStatus.SKIPPED.value:
                    skipped_count += 1

            replied_count = sum(1 for r_id, step_nums in recipient_replied_steps.items() if step.step_number in step_nums)
            pending_count = sum(1 for p_step_id in recipient_pending_step_id.values() if p_step_id == step.id)

            delivered_count = max(0, sent_count - bounced_count)
            delivery_rate = round((delivered_count / sent_count * 100), 1) if sent_count > 0 else 0.0
            reply_rate = round((replied_count / sent_count * 100), 1) if sent_count > 0 else 0.0
            bounce_rate = round((bounced_count / sent_count * 100), 1) if sent_count > 0 else 0.0

            step_analytics_list.append(
                CampaignStepAnalytics(
                    step_id=step.id,
                    step_number=step.step_number,
                    subject=step.subject or f"Step {step.step_number}",
                    delay_hours=step.delay_hours,
                    target_tags=target_tags,
                    targeted_count=targeted_count,
                    sent_count=sent_count,
                    sending_count=sending_count,
                    bounced_count=bounced_count,
                    failed_count=failed_count,
                    skipped_count=skipped_count,
                    replied_count=replied_count,
                    pending_count=pending_count,
                    delivered_count=delivered_count,
                    delivery_rate=delivery_rate,
                    reply_rate=reply_rate,
                    bounce_rate=bounce_rate,
                )
            )

        # 7. Delivery Trend: aggregate daily volume from persisted delivery and recipient records
        daily_trend: dict[str, dict[str, int]] = {}
        for row in deliv_rows:
            d_id, s_id, r_id, status_val, sent_at, bounced_at, thread_id, thread_has_reply, msg_id = row
            if sent_at is not None and status_val == CampaignDeliveryStatus.SENT.value:
                day_str = sent_at.strftime("%Y-%m-%d")
                if day_str not in daily_trend:
                    daily_trend[day_str] = {"sent_count": 0, "bounced_count": 0, "replied_count": 0}
                daily_trend[day_str]["sent_count"] += 1

            if bounced_at is not None or status_val == CampaignDeliveryStatus.BOUNCED.value:
                b_date = bounced_at or sent_at
                if b_date is not None:
                    day_str = b_date.strftime("%Y-%m-%d")
                    if day_str not in daily_trend:
                        daily_trend[day_str] = {"sent_count": 0, "bounced_count": 0, "replied_count": 0}
                    daily_trend[day_str]["bounced_count"] += 1

        # Track unique replying recipients per date to prevent inflating daily reply engagement
        recipients_counted_by_date: dict[str, set[int]] = {}
        for r in recipients:
            if r.id in matched_reply_recipient_ids and r.replied_at is not None:
                day_str = r.replied_at.strftime("%Y-%m-%d")
                if day_str not in daily_trend:
                    daily_trend[day_str] = {"sent_count": 0, "bounced_count": 0, "replied_count": 0}
                if day_str not in recipients_counted_by_date:
                    recipients_counted_by_date[day_str] = set()
                if r.id not in recipients_counted_by_date[day_str]:
                    recipients_counted_by_date[day_str].add(r.id)
                    daily_trend[day_str]["replied_count"] += 1

        for inc_row in incoming_reply_emails:
            inc_sender = inc_row[5]
            inc_sender_clean = parseaddr(inc_sender)[1].strip().lower() if inc_sender else ""
            if not inc_sender_clean or (camp_sender_email and inc_sender_clean == camp_sender_email):
                continue

            inc_date = inc_row[7] or inc_row[6]
            if inc_date is not None:
                day_str = inc_date.strftime("%Y-%m-%d")
                clean_in_reply = (inc_row[3] or "").strip()
                r_id = None
                if clean_in_reply in deliv_by_message_id:
                    cand_deliv = deliv_by_message_id[clean_in_reply]
                    cand_r_id = cand_deliv["recipient_id"]
                    cand_recip = next((r for r in recipients if r.id == cand_r_id), None)
                    if cand_recip and (cand_recip.email or "").strip().lower() == inc_sender_clean:
                        r_id = cand_r_id
                if r_id is not None:
                    if day_str not in daily_trend:
                        daily_trend[day_str] = {"sent_count": 0, "bounced_count": 0, "replied_count": 0}
                    if day_str not in recipients_counted_by_date:
                        recipients_counted_by_date[day_str] = set()
                    if r_id not in recipients_counted_by_date[day_str]:
                        recipients_counted_by_date[day_str].add(r_id)
                        daily_trend[day_str]["replied_count"] += 1

        delivery_trend_points = [
            CampaignDeliveryTrendPoint(
                date=day,
                sent_count=metrics["sent_count"],
                bounced_count=metrics["bounced_count"],
                replied_count=metrics["replied_count"],
            )
            for day, metrics in sorted(daily_trend.items())
        ]

        initial_sent = sum(s.sent_count for s in step_analytics_list if s.step_number == 1)
        followup_sent = sum(s.sent_count for s in step_analytics_list if s.step_number >= 2)
        total_sent = initial_sent + followup_sent

        return CampaignAnalyticsResponse(
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            campaign_status=campaign.status,
            total_recipients=total_recipients,
            total_steps=len(steps),
            initial_sent_count=initial_sent,
            followup_sent_count=followup_sent,
            total_sent_count=total_sent,
            unique_replied_count=len(matched_reply_recipient_ids),
            steps=step_analytics_list,
            delivery_trend=delivery_trend_points,
        )


    @classmethod
    async def get_campaign_emails_drilldown(
        cls,
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        status: Optional[str] = "recipients",
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "desc",
    ) -> Dict[str, Any]:
        """Unified drill-down query for Campaign Emails page supporting 5 performance statuses:
        recipients, sent, replies, bounced, failed.
        Enforces strict company isolation and campaign scoping.
        """
        campaign = await db.get(Campaign, campaign_id)
        if not campaign or campaign.company_id != company_id:
            raise HTTPException(status_code=404, detail="Campaign not found.")

        raw_status = (status or "recipients").strip().lower()
        valid_statuses = ("recipients", "sent", "replies", "bounced", "failed")
        if raw_status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status filter '{status}'. Must be one of: recipients, sent, replies, bounced, failed.")

        search_term = search.strip() if search and search.strip() else None

        # Safe retrieval of campaign sending account
        camp_sender = ""
        if campaign.email_account_id:
            acc = await db.get(EmailAccount, campaign.email_account_id)
            if acc and acc.email_address:
                camp_sender = acc.email_address.strip().lower()

        # Load all deliveries for this campaign (used for reply matching, delivery indexing, etc.)
        deliv_stmt = (
            select(CampaignDelivery, CampaignRecipient, CampaignStep)
            .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
            .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
            .where(CampaignDelivery.campaign_id == campaign_id)
            .order_by(CampaignDelivery.id.desc())
        )
        deliv_res = (await db.execute(deliv_stmt)).all()

        # Index deliveries by message_id and collect thread_ids
        deliv_by_message_id = {}
        campaign_thread_ids = set()
        for d, r, s in deliv_res:
            if d.thread_id:
                campaign_thread_ids.add(d.thread_id)
            if d.message_id:
                clean_m = d.message_id.strip()
                deliv_by_message_id[clean_m] = (d, r, s)
                deliv_by_message_id[clean_m.strip("<>")] = (d, r, s)
                deliv_by_message_id[f"<{clean_m.strip('<>')}>"] = (d, r, s)

        campaign_msg_ids = list(deliv_by_message_id.keys())
        inc_conditions = []
        if campaign_thread_ids:
            inc_conditions.append(Email.thread_id.in_(campaign_thread_ids))
        if campaign_msg_ids:
            mids_slice = campaign_msg_ids[:500]
            inc_conditions.append(Email.in_reply_to.in_(mids_slice))
            ref_clauses = [Email.references_header.contains(mid) for mid in mids_slice if len(mid) > 5]
            if ref_clauses:
                inc_conditions.append(or_(*ref_clauses))

        all_matched_replies = []
        seen_reply_ids = set()
        if inc_conditions:
            inc_stmt = (
                select(Email)
                .where(
                    Email.company_id == company_id,
                    Email.direction == EmailDirection.INCOMING.value,
                    or_(*inc_conditions),
                )
                .order_by(Email.received_at.desc(), Email.id.desc())
            )
            inc_emails = (await db.execute(inc_stmt)).scalars().all()

            for email_obj in inc_emails:
                if email_obj.id in seen_reply_ids:
                    continue
                inc_sender_clean = parseaddr(email_obj.sender)[1].strip().lower() if email_obj.sender else ""
                if not inc_sender_clean or (camp_sender and inc_sender_clean == camp_sender):
                    continue

                cids = []
                if email_obj.in_reply_to:
                    cids.extend(EmailThreadService.extract_message_ids(email_obj.in_reply_to))
                    clean_in = email_obj.in_reply_to.strip()
                    if clean_in not in cids:
                        cids.append(clean_in)
                if email_obj.references_header:
                    for rid in reversed(EmailThreadService.extract_message_ids(email_obj.references_header)):
                        if rid not in cids:
                            cids.append(rid)

                matched_tuple = None
                for cid in cids:
                    if cid in deliv_by_message_id:
                        matched_tuple = deliv_by_message_id[cid]
                        break
                    stripped = cid.strip("<>")
                    if stripped in deliv_by_message_id:
                        matched_tuple = deliv_by_message_id[stripped]
                        break
                    bracketed = f"<{stripped}>"
                    if bracketed in deliv_by_message_id:
                        matched_tuple = deliv_by_message_id[bracketed]
                        break

                if not matched_tuple and email_obj.thread_id:
                    for d, r, s in deliv_res:
                        if d.thread_id == email_obj.thread_id and (r.email or "").strip().lower() == inc_sender_clean:
                            matched_tuple = (d, r, s)
                            break

                if matched_tuple:
                    d, r, s = matched_tuple
                    if (r.email or "").strip().lower() != inc_sender_clean:
                        continue

                    seen_reply_ids.add(email_obj.id)
                    all_matched_replies.append({
                        "id": email_obj.id,
                        "email_id": email_obj.id,
                        "thread_id": email_obj.thread_id,
                        "recipient_id": r.id,
                        "sender": email_obj.sender,
                        "recipient": email_obj.recipients[0] if email_obj.recipients else camp_sender,
                        "email": inc_sender_clean,
                        "recipient_name": f"{r.first_name or ''} {r.last_name or ''}".strip() or None,
                        "subject": email_obj.subject,
                        "received_at": email_obj.received_at or email_obj.sent_at,
                        "sent_at": email_obj.sent_at,
                        "step_number": s.step_number,
                        "delivery_id": d.id,
                    })

        # Summary metrics (shared source of truth for the 5 cards)
        recipients_count = (await db.scalar(
            select(func.count(CampaignRecipient.id)).where(CampaignRecipient.campaign_id == campaign_id)
        )) or 0

        sent_count = (await db.scalar(
            select(func.count(CampaignDelivery.id)).where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.status == CampaignDeliveryStatus.SENT.value,
                CampaignDelivery.bounced_at.is_(None),
            )
        )) or 0

        bounced_count = (await db.scalar(
            select(func.count(CampaignDelivery.id)).where(
                CampaignDelivery.campaign_id == campaign_id,
                or_(
                    CampaignDelivery.status == CampaignDeliveryStatus.BOUNCED.value,
                    CampaignDelivery.bounced_at.is_not(None),
                ),
            )
        )) or 0

        failed_count = (await db.scalar(
            select(func.count(CampaignDelivery.id)).where(
                CampaignDelivery.campaign_id == campaign_id,
                CampaignDelivery.status == CampaignDeliveryStatus.FAILED.value,
                CampaignDelivery.bounced_at.is_(None),
            )
        )) or 0

        replies_count = len(all_matched_replies)

        summary = {
            "recipients_count": recipients_count,
            "sent_count": sent_count,
            "replies_count": replies_count,
            "bounced_count": bounced_count,
            "failed_count": failed_count,
        }

        items = []
        total = 0

        if raw_status == "recipients":
            base_q = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
            if search_term:
                s = f"%{search_term}%"
                base_q = base_q.where(
                    or_(
                        CampaignRecipient.email.ilike(s),
                        CampaignRecipient.first_name.ilike(s),
                        CampaignRecipient.last_name.ilike(s),
                    )
                )
            count_q = select(func.count()).select_from(base_q.subquery())
            total = (await db.scalar(count_q)) or 0

            if sort_by == "email":
                order_col = CampaignRecipient.email.desc() if sort_order == "desc" else CampaignRecipient.email.asc()
            else:
                order_col = CampaignRecipient.created_at.desc() if sort_order == "desc" else CampaignRecipient.created_at.asc()

            paged_q = base_q.order_by(order_col, CampaignRecipient.id.desc()).offset(offset).limit(limit)
            recip_rows = (await db.execute(paged_q)).scalars().all()
            for r in recip_rows:
                items.append({
                    "id": r.id,
                    "recipient_id": r.id,
                    "email": r.email,
                    "recipient_name": f"{r.first_name or ''} {r.last_name or ''}".strip() or None,
                    "status": r.status,
                    "stopped_reason": r.stopped_reason,
                    "step_number": r.current_step_number,
                    "replied_at": r.replied_at,
                    "created_at": r.created_at,
                    "next_step_due_at": r.next_step_due_at,
                })

        elif raw_status == "sent":
            base_q = (
                select(CampaignDelivery, CampaignRecipient, CampaignStep)
                .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
                .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
                .where(
                    CampaignDelivery.campaign_id == campaign_id,
                    CampaignDelivery.status == CampaignDeliveryStatus.SENT.value,
                    CampaignDelivery.bounced_at.is_(None),
                )
            )
            if search_term:
                s = f"%{search_term}%"
                base_q = base_q.where(
                    or_(
                        CampaignRecipient.email.ilike(s),
                        CampaignRecipient.first_name.ilike(s),
                        CampaignRecipient.last_name.ilike(s),
                        CampaignStep.subject.ilike(s),
                    )
                )
            count_q = select(func.count()).select_from(base_q.subquery())
            total = (await db.scalar(count_q)) or 0

            order_col = CampaignDelivery.sent_at.desc() if sort_order == "desc" else CampaignDelivery.sent_at.asc()
            paged_q = base_q.order_by(order_col, CampaignDelivery.id.desc()).offset(offset).limit(limit)
            rows = (await db.execute(paged_q)).all()
            for deliv, recip, step in rows:
                items.append({
                    "id": deliv.id,
                    "delivery_id": deliv.id,
                    "recipient_id": recip.id,
                    "email_id": deliv.email_id,
                    "thread_id": deliv.thread_id,
                    "email": recip.email,
                    "recipient_name": f"{recip.first_name or ''} {recip.last_name or ''}".strip() or None,
                    "subject": step.subject,
                    "step_number": step.step_number,
                    "sent_at": deliv.sent_at or deliv.created_at,
                    "status": deliv.status,
                })

        elif raw_status == "replies":
            filtered_replies = all_matched_replies
            if search_term:
                st = search_term.lower()
                filtered_replies = [
                    item for item in all_matched_replies
                    if st in (item.get("sender") or "").lower()
                    or st in (item.get("recipient") or "").lower()
                    or st in (item.get("email") or "").lower()
                    or st in (item.get("subject") or "").lower()
                    or st in (item.get("recipient_name") or "").lower()
                ]
            total = len(filtered_replies)
            items = filtered_replies[offset : offset + limit]

        elif raw_status == "bounced":
            base_q = (
                select(CampaignDelivery, CampaignRecipient, CampaignStep)
                .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
                .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
                .where(
                    CampaignDelivery.campaign_id == campaign_id,
                    or_(
                        CampaignDelivery.status == CampaignDeliveryStatus.BOUNCED.value,
                        CampaignDelivery.bounced_at.is_not(None),
                    ),
                )
            )
            if search_term:
                s = f"%{search_term}%"
                base_q = base_q.where(
                    or_(
                        CampaignRecipient.email.ilike(s),
                        CampaignRecipient.first_name.ilike(s),
                        CampaignRecipient.last_name.ilike(s),
                        CampaignStep.subject.ilike(s),
                        CampaignDelivery.error_message.ilike(s),
                    )
                )
            count_q = select(func.count()).select_from(base_q.subquery())
            total = (await db.scalar(count_q)) or 0

            order_col = CampaignDelivery.bounced_at.desc() if sort_order == "desc" else CampaignDelivery.bounced_at.asc()
            paged_q = base_q.order_by(order_col, CampaignDelivery.id.desc()).offset(offset).limit(limit)
            rows = (await db.execute(paged_q)).all()

            recip_emails = [recip.email.strip().lower() for _, recip, _ in rows if recip.email]
            suppr_map = {}
            if recip_emails:
                sup_stmt = select(SuppressionEntry).where(
                    SuppressionEntry.company_id == company_id,
                    func.lower(SuppressionEntry.email).in_(recip_emails),
                )
                sup_rows = (await db.execute(sup_stmt)).scalars().all()
                for sup in sup_rows:
                    suppr_map[sup.email.strip().lower()] = sup

            for deliv, recip, step in rows:
                norm_e = (recip.email or "").strip().lower()
                suppr_obj = suppr_map.get(norm_e)
                items.append({
                    "id": deliv.id,
                    "delivery_id": deliv.id,
                    "recipient_id": recip.id,
                    "email_id": deliv.email_id,
                    "thread_id": deliv.thread_id,
                    "email": recip.email,
                    "recipient_name": f"{recip.first_name or ''} {recip.last_name or ''}".strip() or None,
                    "subject": step.subject,
                    "step_number": step.step_number,
                    "status": deliv.status,
                    "stopped_reason": recip.stopped_reason,
                    "bounce_type": (deliv.error_message if deliv.error_message else (suppr_obj.reason if suppr_obj else "Hard Bounce")),
                    "error_message": deliv.error_message or "Recipient mailbox bounced / rejected",
                    "bounced_at": deliv.bounced_at or deliv.sent_at or deliv.created_at,
                    "is_suppressed": suppr_obj is not None,
                    "suppression_reason": suppr_obj.reason if suppr_obj else None,
                })

        elif raw_status == "failed":
            base_q = (
                select(CampaignDelivery, CampaignRecipient, CampaignStep)
                .join(CampaignRecipient, CampaignDelivery.recipient_id == CampaignRecipient.id)
                .join(CampaignStep, CampaignDelivery.step_id == CampaignStep.id)
                .where(
                    CampaignDelivery.campaign_id == campaign_id,
                    CampaignDelivery.status == CampaignDeliveryStatus.FAILED.value,
                    CampaignDelivery.bounced_at.is_(None),
                )
            )
            if search_term:
                s = f"%{search_term}%"
                base_q = base_q.where(
                    or_(
                        CampaignRecipient.email.ilike(s),
                        CampaignRecipient.first_name.ilike(s),
                        CampaignRecipient.last_name.ilike(s),
                        CampaignStep.subject.ilike(s),
                        CampaignDelivery.error_message.ilike(s),
                    )
                )
            count_q = select(func.count()).select_from(base_q.subquery())
            total = (await db.scalar(count_q)) or 0

            order_col = CampaignDelivery.last_attempt_at.desc() if sort_order == "desc" else CampaignDelivery.last_attempt_at.asc()
            paged_q = base_q.order_by(order_col, CampaignDelivery.id.desc()).offset(offset).limit(limit)
            rows = (await db.execute(paged_q)).all()
            for deliv, recip, step in rows:
                items.append({
                    "id": deliv.id,
                    "delivery_id": deliv.id,
                    "recipient_id": recip.id,
                    "email": recip.email,
                    "recipient_name": f"{recip.first_name or ''} {recip.last_name or ''}".strip() or None,
                    "subject": step.subject,
                    "error_message": deliv.error_message or "Delivery dispatch failed",
                    "attempt_count": deliv.attempt_count or 1,
                    "last_attempt_at": deliv.last_attempt_at or deliv.created_at,
                    "step_number": step.step_number,
                    "status": deliv.status,
                    "can_retry": True,
                })

        return {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "selected_status": raw_status,
            "summary": summary,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }
