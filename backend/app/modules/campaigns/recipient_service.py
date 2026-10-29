import csv
from datetime import datetime, timedelta, timezone
import io
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignDelivery,
    CampaignDeliveryStatus,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignRecipientStopReason,
    CampaignStep,
    CampaignStatus,
)
from app.modules.campaigns.schemas import (
    CampaignRecipientBulkCreateResponse,
    CampaignRecipientCreate,
    CampaignRecipientImportResponse,
    CampaignRecipientRead,
    CampaignRecipientUpdate,
    normalize_and_validate_email,
    normalize_and_validate_tag,
    normalize_and_validate_tag_list,
)
from app.modules.campaigns.service import CampaignService
from app.modules.campaigns.suppression_service import SuppressionService

MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 Megabytes practical file size limit


class CampaignRecipientService:
    """Service layer managing campaign recipients, normalization, duplicate prevention, and CSV import."""

    @staticmethod
    async def get_draft_campaign(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Verify campaign belongs to the company and is in editable DRAFT status.
        
        Returns 404 for cross-company access (anti-enumeration).
        Returns 400 if campaign is not in DRAFT.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status != CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot modify recipients for campaign with status '{campaign.status}'. Recipients can only be modified when campaign is in DRAFT.",
            )
        return campaign

    @staticmethod
    async def get_campaign_read(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> Campaign:
        """Verify campaign belongs to the company for read-only recipient access."""
        return await CampaignService.get_campaign(db, company_id, campaign_id)

    @staticmethod
    async def create_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_in: CampaignRecipientCreate,
    ) -> CampaignRecipient:
        """Add a single recipient to a DRAFT campaign.
        
        Enforces normalized email uniqueness within the campaign.
        Initial recipient status is always PENDING.
        """
        await CampaignRecipientService.get_draft_campaign(db, company_id, campaign_id)
        norm_email = normalize_and_validate_email(recipient_in.email)

        # Check for existing recipient with this normalized email in the campaign
        existing = await db.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.email == norm_email,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recipient with email '{norm_email}' already exists in this campaign.",
            )

        custom_vars = dict(recipient_in.custom_variables) if recipient_in.custom_variables else {}
        if recipient_in.tags is not None:
            custom_vars["tags"] = recipient_in.tags

        recipient = CampaignRecipient(
            campaign_id=campaign_id,
            email=norm_email,
            first_name=recipient_in.first_name,
            last_name=recipient_in.last_name,
            custom_variables=custom_vars,
            status=CampaignRecipientStatus.PENDING.value,
        )
        db.add(recipient)
        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def bulk_create_recipients(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipients_in: List[CampaignRecipientCreate],
    ) -> CampaignRecipientBulkCreateResponse:
        """Add multiple recipients to a DRAFT campaign with batch deduplication.
        
        Deduplicates normalized addresses within the batch and checks against existing
        campaign recipients in a single efficient database query.
        """
        await CampaignRecipientService.get_draft_campaign(db, company_id, campaign_id)

        seen_emails: Set[str] = set()
        unique_incoming: List[Tuple[str, CampaignRecipientCreate]] = []
        skipped_emails: List[str] = []

        # 1. In-memory deduplication within the request batch
        for item in recipients_in:
            norm_email = normalize_and_validate_email(item.email)
            if norm_email in seen_emails:
                skipped_emails.append(norm_email)
            else:
                seen_emails.add(norm_email)
                unique_incoming.append((norm_email, item))

        # 2. Check existing recipients in database using a single query
        existing_in_db: Set[str] = set()
        if seen_emails:
            existing_result = await db.execute(
                select(CampaignRecipient.email).where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.email.in_(seen_emails),
                )
            )
            existing_in_db = set(existing_result.scalars().all())

        # 3. Create only new non-duplicate recipients
        new_recipients: List[CampaignRecipient] = []
        for norm_email, item in unique_incoming:
            if norm_email in existing_in_db:
                skipped_emails.append(norm_email)
            else:
                cv = dict(item.custom_variables) if item.custom_variables else {}
                if item.tags is not None:
                    cv["tags"] = item.tags
                new_recipients.append(
                    CampaignRecipient(
                        campaign_id=campaign_id,
                        email=norm_email,
                        first_name=item.first_name,
                        last_name=item.last_name,
                        custom_variables=cv,
                        status=CampaignRecipientStatus.PENDING.value,
                    )
                )

        if new_recipients:
            db.add_all(new_recipients)
            await db.commit()
            for r in new_recipients:
                await db.refresh(r)

        return CampaignRecipientBulkCreateResponse(
            total_submitted=len(recipients_in),
            inserted_count=len(new_recipients),
            skipped_count=len(skipped_emails),
            recipients=[CampaignRecipientRead.model_validate(r) for r in new_recipients],
            skipped_emails=skipped_emails,
        )

    @staticmethod
    async def list_recipients(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CampaignRecipient]:
        """List recipients belonging strictly to the specified campaign.
        
        Supports pagination, status filtering, and substring search on email.
        """
        await CampaignRecipientService.get_campaign_read(db, company_id, campaign_id)

        query = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)

        if status_filter:
            norm_status = status_filter.strip().upper()
            query = query.where(CampaignRecipient.status == norm_status)

        if search:
            query = query.where(CampaignRecipient.email.ilike(f"%{search.strip().lower()}%"))

        query = query.order_by(CampaignRecipient.created_at.desc(), CampaignRecipient.id.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
    ) -> CampaignRecipient:
        """Retrieve a specific recipient within a campaign.
        
        Enforces strict company and campaign isolation with 404 anti-enumeration.
        """
        await CampaignRecipientService.get_campaign_read(db, company_id, campaign_id)

        result = await db.execute(
            select(CampaignRecipient).where(
                CampaignRecipient.id == recipient_id,
                CampaignRecipient.campaign_id == campaign_id,
            )
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign recipient not found.",
            )
        return recipient

    @staticmethod
    async def update_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        recipient_update: CampaignRecipientUpdate,
    ) -> CampaignRecipient:
        """Update an existing recipient in a DRAFT campaign.
        
        Rejects modifications if campaign is not in DRAFT.
        If email is changed, normalizes, validates syntax, and enforces uniqueness.
        Direct updates to status or lifecycle fields are forbidden.
        """
        await CampaignRecipientService.get_draft_campaign(db, company_id, campaign_id)
        recipient = await CampaignRecipientService.get_recipient(db, company_id, campaign_id, recipient_id)

        update_data = recipient_update.model_dump(exclude_unset=True)

        if "email" in update_data and update_data["email"] is not None:
            norm_email = normalize_and_validate_email(update_data["email"])
            if norm_email != recipient.email:
                existing = await db.execute(
                    select(CampaignRecipient).where(
                        CampaignRecipient.campaign_id == campaign_id,
                        CampaignRecipient.email == norm_email,
                        CampaignRecipient.id != recipient_id,
                    )
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Recipient with email '{norm_email}' already exists in this campaign.",
                    )
                recipient.email = norm_email

        if "first_name" in update_data:
            recipient.first_name = update_data["first_name"]
        if "last_name" in update_data:
            recipient.last_name = update_data["last_name"]
        if "custom_variables" in update_data:
            recipient.custom_variables = update_data["custom_variables"]
        if "tags" in update_data:
            recipient.set_tags(update_data["tags"] or [])

        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def delete_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
    ) -> None:
        """Delete a recipient from a DRAFT campaign.
        
        Rejects deletion if campaign is not in DRAFT.
        """
        await CampaignRecipientService.get_draft_campaign(db, company_id, campaign_id)
        recipient = await CampaignRecipientService.get_recipient(db, company_id, campaign_id, recipient_id)

        await db.delete(recipient)
        await db.commit()

    @staticmethod
    async def import_recipients_csv(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        file: UploadFile,
    ) -> CampaignRecipientImportResponse:
        """Import recipients from an uploaded CSV file into a DRAFT campaign.
        
        Validates structure, normalizes email addresses, deduplicates within the CSV and DB,
        and transactionally inserts valid new recipients.
        """
        await CampaignRecipientService.get_draft_campaign(db, company_id, campaign_id)

        # 1. Read and validate raw file payload
        content = await file.read()
        if not content or len(content.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file is empty.",
            )

        if len(content) > MAX_CSV_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV file exceeds maximum allowed size of {MAX_CSV_BYTES // (1024 * 1024)}MB.",
            )

        # 2. Decode text stream
        text: Optional[str] = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to decode CSV file. Please upload a UTF-8 encoded CSV.",
            )

        # 3. Parse CSV rows
        stream = io.StringIO(text)
        reader = csv.reader(stream)

        try:
            raw_headers = next(reader)
        except StopIteration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file contains no header row.",
            )

        headers = [h.strip().lower() for h in raw_headers]
        if "email" not in headers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file must contain an 'email' column header.",
            )

        email_idx = headers.index("email")
        first_name_idx = next(
            (i for i, h in enumerate(headers) if h in ("first_name", "firstname", "first name")),
            None,
        )
        last_name_idx = next(
            (i for i, h in enumerate(headers) if h in ("last_name", "lastname", "last name")),
            None,
        )
        custom_vars_idx = next(
            (i for i, h in enumerate(headers) if h in ("custom_variables", "custom variables", "variables")),
            None,
        )
        tags_idx = next(
            (i for i, h in enumerate(headers) if h in ("tags", "tag", "labels", "recipient_tags")),
            None,
        )

        seen_emails: Set[str] = set()
        valid_rows: List[Tuple[str, Optional[str], Optional[str], Optional[Dict[str, Any]]]] = []
        skipped_emails: List[str] = []
        invalid_rows: List[Dict[str, Any]] = []

        row_num = 1  # Header was row 1
        for row in reader:
            row_num += 1
            if not row or all(c.strip() == "" for c in row):
                continue  # Skip empty blank rows

            if email_idx >= len(row) or not row[email_idx].strip():
                invalid_rows.append({"row": row_num, "email": "", "reason": "Missing or empty email address"})
                continue

            raw_email = row[email_idx]
            try:
                norm_email = normalize_and_validate_email(raw_email)
            except ValueError as err:
                invalid_rows.append({"row": row_num, "email": raw_email, "reason": str(err)})
                continue

            if norm_email in seen_emails:
                skipped_emails.append(norm_email)
                continue
            seen_emails.add(norm_email)

            first_name = (
                row[first_name_idx].strip()
                if first_name_idx is not None and first_name_idx < len(row) and row[first_name_idx].strip()
                else None
            )
            last_name = (
                row[last_name_idx].strip()
                if last_name_idx is not None and last_name_idx < len(row) and row[last_name_idx].strip()
                else None
            )

            custom_vars: Optional[Dict[str, Any]] = None
            if custom_vars_idx is not None and custom_vars_idx < len(row) and row[custom_vars_idx].strip():
                raw_vars = row[custom_vars_idx].strip()
                try:
                    parsed_vars = json.loads(raw_vars)
                    if isinstance(parsed_vars, dict):
                        custom_vars = parsed_vars
                    else:
                        custom_vars = {"value": parsed_vars}
                except Exception:
                    custom_vars = {"raw": raw_vars}

            raw_tags = (
                row[tags_idx].strip()
                if tags_idx is not None and tags_idx < len(row) and row[tags_idx].strip()
                else None
            )
            if raw_tags:
                delims = [",", ";", "|"]
                delim = ","
                for d in delims:
                    if d in raw_tags:
                        delim = d
                        break
                candidates = [t.strip() for t in raw_tags.split(delim) if t.strip()]
                parsed_tags = normalize_and_validate_tag_list(candidates)
                if parsed_tags:
                    if custom_vars is None:
                        custom_vars = {}
                    custom_vars["tags"] = parsed_tags

            valid_rows.append((norm_email, first_name, last_name, custom_vars))

        # 4. Check existing recipients in database with a single query
        existing_in_db: Set[str] = set()
        if seen_emails:
            existing_result = await db.execute(
                select(CampaignRecipient.email).where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.email.in_(seen_emails),
                )
            )
            existing_in_db = set(existing_result.scalars().all())

        # 5. Build and insert new recipients
        new_recipients: List[CampaignRecipient] = []
        for norm_email, fn, ln, cv in valid_rows:
            if norm_email in existing_in_db:
                skipped_emails.append(norm_email)
            else:
                new_recipients.append(
                    CampaignRecipient(
                        campaign_id=campaign_id,
                        email=norm_email,
                        first_name=fn,
                        last_name=ln,
                        custom_variables=cv,
                        status=CampaignRecipientStatus.PENDING.value,
                    )
                )

        if new_recipients:
            db.add_all(new_recipients)
            await db.commit()

        total_rows_count = len(new_recipients) + len(skipped_emails) + len(invalid_rows)

        return CampaignRecipientImportResponse(
            total_rows=total_rows_count,
            inserted_count=len(new_recipients),
            skipped_duplicates_count=len(skipped_emails),
            invalid_rows_count=len(invalid_rows),
            skipped_emails=skipped_emails,
            invalid_rows=invalid_rows,
        )


    @staticmethod
    async def stop_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        reason: str = "MANUAL",
    ) -> CampaignRecipient:
        """Stop future initial or follow-up sends for a recipient, clear pending timer, and record MANUAL stop reason.
        
        - Enforces company isolation via campaign lookup.
        - Synchronizes with due-follow-up workers via row-level lock (with_for_update).
        - Idempotent if recipient was already manually stopped.
        - Rejects terminal recipients (replied, bounced, unsubscribed, suppressed, completed).
        - Rejects if campaign is in DRAFT.
        - Cancels any PENDING deliveries.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status == CampaignStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: campaign is still in DRAFT status. Recipients can be deleted or edited directly.",
            )

        stmt = (
            select(CampaignRecipient)
            .where(
                CampaignRecipient.id == recipient_id,
                CampaignRecipient.campaign_id == campaign_id,
            )
            .with_for_update()
        )
        res = await db.execute(stmt)
        recipient = res.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign recipient not found.",
            )

        if (
            recipient.status == CampaignRecipientStatus.STOPPED.value
            and recipient.stopped_reason == CampaignRecipientStopReason.MANUAL.value
        ):
            return recipient

        if recipient.replied_at is not None or recipient.stopped_reason == CampaignRecipientStopReason.REPLIED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: recipient has already replied.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.BOUNCED.value or recipient.status == CampaignRecipientStatus.BOUNCED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: recipient has bounced.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: recipient has unsubscribed.",
            )
        if recipient.status == CampaignRecipientStatus.SUPPRESSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: recipient is on the suppression list.",
            )
        if recipient.status == CampaignRecipientStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot stop recipient: recipient has already completed the sequence.",
            )

        pending_delivs_stmt = select(CampaignDelivery).where(
            CampaignDelivery.campaign_id == campaign_id,
            CampaignDelivery.recipient_id == recipient_id,
            CampaignDelivery.status == CampaignDeliveryStatus.PENDING.value,
        )
        deliv_res = await db.execute(pending_delivs_stmt)
        for deliv in deliv_res.scalars().all():
            deliv.status = CampaignDeliveryStatus.FAILED.value
            deliv.error_message = "Delivery cancelled: recipient stopped manually"

        recipient.status = CampaignRecipientStatus.STOPPED.value
        recipient.stopped_reason = CampaignRecipientStopReason.MANUAL.value
        recipient.next_step_due_at = None

        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def skip_recipient_next_step(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
    ) -> CampaignRecipient:
        """Skip the next pending follow-up step without dispatching it.
        
        Advances recipient.current_step_number to the skipped step, records SKIPPED delivery,
        and either schedules the subsequent configured active step or marks the sequence COMPLETED.
        - Enforces company isolation.
        - Rejects terminal, suppressed, stopped, or completed recipients.
        - Rejects campaigns that are DRAFT, CANCELLED, or ARCHIVED.
        - Synchronizes with due-follow-up workers via row-level lock.
        """
        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status in (
            CampaignStatus.DRAFT.value,
            CampaignStatus.CANCELLED.value,
            CampaignStatus.ARCHIVED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot skip steps for campaign with status '{campaign.status}'.",
            )

        stmt = (
            select(CampaignRecipient)
            .where(
                CampaignRecipient.id == recipient_id,
                CampaignRecipient.campaign_id == campaign_id,
            )
            .with_for_update()
        )
        res = await db.execute(stmt)
        recipient = res.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign recipient not found.",
            )

        if await SuppressionService.is_suppressed(db, company_id, recipient.email):
            recipient.status = CampaignRecipientStatus.SUPPRESSED.value
            recipient.next_step_due_at = None
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: recipient is on the company suppression list.",
            )

        if recipient.replied_at is not None or recipient.stopped_reason == CampaignRecipientStopReason.REPLIED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: recipient has already replied.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.BOUNCED.value or recipient.status == CampaignRecipientStatus.BOUNCED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: recipient has bounced.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: recipient has unsubscribed.",
            )
        if recipient.status == CampaignRecipientStatus.STOPPED.value or recipient.stopped_reason is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot skip step: recipient is stopped ({recipient.stopped_reason or 'STOPPED'}).",
            )
        if recipient.status == CampaignRecipientStatus.SUPPRESSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: recipient is suppressed.",
            )
        if recipient.status == CampaignRecipientStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip step: sequence is already completed.",
            )

        skipped_step_number = recipient.current_step_number + 1
        step_stmt = select(CampaignStep).where(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.step_number == skipped_step_number,
            CampaignStep.is_active == True,
        )
        step_to_skip = (await db.execute(step_stmt)).scalar_one_or_none()
        if not step_to_skip:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No active Step {skipped_step_number} found to skip.",
            )

        delivery_stmt = select(CampaignDelivery).where(
            CampaignDelivery.campaign_id == campaign_id,
            CampaignDelivery.recipient_id == recipient_id,
            CampaignDelivery.step_id == step_to_skip.id,
        )
        deliv = (await db.execute(delivery_stmt)).scalar_one_or_none()
        if deliv:
            deliv.status = CampaignDeliveryStatus.SKIPPED.value
            deliv.error_message = "Step skipped by administrator"
        else:
            deliv = CampaignDelivery(
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                step_id=step_to_skip.id,
                status=CampaignDeliveryStatus.SKIPPED.value,
                error_message="Step skipped by administrator",
            )
            db.add(deliv)

        recipient.current_step_number = skipped_step_number

        subseq_stmt = (
            select(CampaignStep)
            .where(
                CampaignStep.campaign_id == campaign_id,
                CampaignStep.step_number > skipped_step_number,
                CampaignStep.is_active == True,
            )
            .order_by(CampaignStep.step_number.asc())
        )
        subseq_step = (await db.execute(subseq_stmt)).scalars().first()
        if subseq_step:
            now_utc = datetime.now(timezone.utc)
            candidate_due = now_utc + timedelta(hours=subseq_step.delay_hours)
            recipient.next_step_due_at = candidate_due
            recipient.status = CampaignRecipientStatus.SENT.value
        else:
            recipient.next_step_due_at = None
            recipient.status = CampaignRecipientStatus.COMPLETED.value

        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def reschedule_recipient(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        rescheduled_due_at: datetime,
    ) -> CampaignRecipient:
        """Reschedule the next pending follow-up step for a recipient.
        
        - Enforces company isolation.
        - Validates that rescheduled_due_at is timezone-aware and in the future.
        - Rejects terminal, suppressed, stopped, or completed recipients.
        - Rejects campaigns that are DRAFT, CANCELLED, or ARCHIVED.
        - Verifies that an active next step exists to be scheduled.
        - Synchronizes with due-follow-up workers via row-level lock.
        """
        if rescheduled_due_at.tzinfo is None:
            rescheduled_due_at = rescheduled_due_at.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        if rescheduled_due_at <= now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rescheduled time must be in the future.",
            )

        campaign = await CampaignService.get_campaign(db, company_id, campaign_id)
        if campaign.status in (
            CampaignStatus.DRAFT.value,
            CampaignStatus.CANCELLED.value,
            CampaignStatus.ARCHIVED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reschedule follow-up for campaign with status '{campaign.status}'.",
            )

        stmt = (
            select(CampaignRecipient)
            .where(
                CampaignRecipient.id == recipient_id,
                CampaignRecipient.campaign_id == campaign_id,
            )
            .with_for_update()
        )
        res = await db.execute(stmt)
        recipient = res.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign recipient not found.",
            )

        if await SuppressionService.is_suppressed(db, company_id, recipient.email):
            recipient.status = CampaignRecipientStatus.SUPPRESSED.value
            recipient.next_step_due_at = None
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule follow-up: recipient is on the company suppression list.",
            )

        if recipient.replied_at is not None or recipient.stopped_reason == CampaignRecipientStopReason.REPLIED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule: recipient has already replied.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.BOUNCED.value or recipient.status == CampaignRecipientStatus.BOUNCED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule: recipient has bounced.",
            )
        if recipient.stopped_reason == CampaignRecipientStopReason.UNSUBSCRIBED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule: recipient has unsubscribed.",
            )
        if recipient.status == CampaignRecipientStatus.STOPPED.value or recipient.stopped_reason is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reschedule: recipient is stopped ({recipient.stopped_reason or 'STOPPED'}).",
            )
        if recipient.status == CampaignRecipientStatus.SUPPRESSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule: recipient is suppressed.",
            )
        if recipient.status == CampaignRecipientStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule: sequence is already completed.",
            )

        next_step_number = recipient.current_step_number + 1
        step_stmt = select(CampaignStep).where(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.step_number == next_step_number,
            CampaignStep.is_active == True,
        )
        next_step = (await db.execute(step_stmt)).scalar_one_or_none()
        if not next_step:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No active follow-up step (Step {next_step_number}) found to reschedule.",
            )

        recipient.next_step_due_at = rescheduled_due_at
        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def update_recipient_tags(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        tags: List[str],
    ) -> CampaignRecipient:
        """Replace all tags of a campaign recipient."""
        recipient = await CampaignRecipientService.get_recipient(db, company_id, campaign_id, recipient_id)
        validated_tags = normalize_and_validate_tag_list(tags)
        recipient.set_tags(validated_tags)
        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def add_recipient_tag(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        tag: str,
    ) -> CampaignRecipient:
        """Add a single tag to a campaign recipient."""
        recipient = await CampaignRecipientService.get_recipient(db, company_id, campaign_id, recipient_id)
        norm_tag = normalize_and_validate_tag(tag)
        current_tags = list(recipient.tags)
        if norm_tag not in current_tags:
            current_tags.append(norm_tag)
            recipient.set_tags(current_tags)
            await db.commit()
            await db.refresh(recipient)
        return recipient

    @staticmethod
    async def remove_recipient_tag(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
        recipient_id: int,
        tag: str,
    ) -> CampaignRecipient:
        """Remove a single tag from a campaign recipient."""
        recipient = await CampaignRecipientService.get_recipient(db, company_id, campaign_id, recipient_id)
        norm_tag = normalize_and_validate_tag(tag)
        current_tags = [t for t in recipient.tags if t != norm_tag]
        recipient.set_tags(current_tags)
        await db.commit()
        await db.refresh(recipient)
        return recipient

    @staticmethod
    async def get_campaign_tags(
        db: AsyncSession,
        company_id: int,
        campaign_id: int,
    ) -> List[str]:
        """Get all unique tags used across recipients and steps in a campaign."""
        await CampaignRecipientService.get_campaign_read(db, company_id, campaign_id)

        recip_stmt = select(CampaignRecipient.custom_variables).where(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.custom_variables.is_not(None),
        )
        recip_res = await db.execute(recip_stmt)
        unique_tags: Set[str] = set()
        for cv in recip_res.scalars().all():
            if isinstance(cv, dict):
                tags_val = cv.get("tags")
                if isinstance(tags_val, list):
                    for t in tags_val:
                        if isinstance(t, str) and t.strip():
                            unique_tags.add(t.strip().lower())

        step_stmt = select(CampaignStep.target_tags).where(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.target_tags.is_not(None),
        )
        step_res = await db.execute(step_stmt)
        for tt in step_res.scalars().all():
            if isinstance(tt, list):
                for t in tt:
                    if isinstance(t, str) and t.strip():
                        unique_tags.add(t.strip().lower())

        return sorted(list(unique_tags))
