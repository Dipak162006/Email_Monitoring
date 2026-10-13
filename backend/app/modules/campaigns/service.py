from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
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
    CampaignStatus,
)
from app.modules.campaigns.schemas import (
    CampaignAttachmentRead,
    CampaignCreate,
    CampaignDetailRead,
    CampaignUpdate,
)
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService


# Backend-owned campaign lifecycle state machine transition graph
VALID_TRANSITIONS: dict[str, Set[str]] = {
    CampaignStatus.DRAFT.value: {
        CampaignStatus.SCHEDULED.value,
        CampaignStatus.QUEUED.value,
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
    CampaignStatus.COMPLETED.value: set(),
    CampaignStatus.CANCELLED.value: set(),
    CampaignStatus.FAILED.value: set(),
}

TERMINAL_STATES: Set[str] = {
    CampaignStatus.COMPLETED.value,
    CampaignStatus.CANCELLED.value,
    CampaignStatus.FAILED.value,
}

DELETABLE_STATES: Set[str] = {
    CampaignStatus.DRAFT.value,
    CampaignStatus.COMPLETED.value,
    CampaignStatus.CANCELLED.value,
    CampaignStatus.FAILED.value,
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
        """
        # Validate sender email account
        await CampaignService.get_email_account_for_company(
            db=db,
            company_id=company_id,
            email_account_id=campaign_in.email_account_id,
        )

        campaign = Campaign(
            company_id=company_id,
            email_account_id=campaign_in.email_account_id,
            name=campaign_in.name,
            subject=campaign_in.subject,
            body_text=campaign_in.body_text,
            body_html=campaign_in.body_html,
            send_interval_seconds=campaign_in.send_interval_seconds,
            status=CampaignStatus.DRAFT.value,
            created_by_user_id=creator_user_id,
        )
        db.add(campaign)
        await db.commit()
        return await CampaignService.get_campaign(db, company_id, campaign.id)

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
            .options(selectinload(Campaign.attachments))
            .where(Campaign.company_id == company_id)
        )

        if status_filter:
            norm_status = status_filter.strip().upper()
            query = query.where(Campaign.status == norm_status)

        query = query.order_by(Campaign.created_at.desc(), Campaign.id.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        rows = result.all()
        campaigns: List[Campaign] = []
        for campaign, count in rows:
            campaign.recipient_count = count or 0
            campaigns.append(campaign)
        return campaigns

    @staticmethod
    async def update_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        campaign_update: CampaignUpdate,
    ) -> Campaign:
        """Update campaign configuration fields.
        
        Only campaigns in DRAFT status may be modified.
        If email_account_id is changed, validates company ownership and active state.
        Direct updates to status or lifecycle timestamps are rejected.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

        if campaign.status != CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit campaign with status '{campaign.status}'. Only DRAFT campaigns can be edited.",
            )

        update_data = campaign_update.model_dump(exclude_unset=True)

        if "email_account_id" in update_data and update_data["email_account_id"] is not None:
            await CampaignService.get_email_account_for_company(
                db=db,
                company_id=company_id,
                email_account_id=update_data["email_account_id"],
            )

        for field, value in update_data.items():
            setattr(campaign, field, value)

        await db.commit()
        return await CampaignService.get_campaign(db, company_id, campaign.id)

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
        return await CampaignService.transition_state(db, company_id, campaign_id, CampaignStatus.CANCELLED)

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
    def to_detail_schema(
        campaign: Campaign,
        recipient_count: Optional[int] = None,
    ) -> CampaignDetailRead:
        """Convert a Campaign model instance into a CampaignDetailRead schema."""
        email_account = campaign.__dict__.get("email_account")
        recipients = campaign.__dict__.get("recipients")
        attachments = campaign.__dict__.get("attachments") or []
        final_count = (
            recipient_count
            if recipient_count is not None
            else (len(recipients) if recipients is not None else 0)
        )
        return CampaignDetailRead(
            id=campaign.id,
            company_id=campaign.company_id,
            email_account_id=campaign.email_account_id,
            name=campaign.name,
            subject=campaign.subject,
            body_text=campaign.body_text,
            body_html=campaign.body_html,
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
            attachments=[CampaignAttachmentRead.model_validate(a) for a in attachments],
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

        await db.commit()
        await db.refresh(campaign)
        return await CampaignService.get_campaign(db, company_id, campaign_id)

