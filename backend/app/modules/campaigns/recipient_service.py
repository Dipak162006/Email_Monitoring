import csv
import io
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientStatus,
    CampaignStatus,
)
from app.modules.campaigns.schemas import (
    CampaignRecipientBulkCreateResponse,
    CampaignRecipientCreate,
    CampaignRecipientImportResponse,
    CampaignRecipientRead,
    CampaignRecipientUpdate,
    normalize_and_validate_email,
)
from app.modules.campaigns.service import CampaignService

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

        recipient = CampaignRecipient(
            campaign_id=campaign_id,
            email=norm_email,
            first_name=recipient_in.first_name,
            last_name=recipient_in.last_name,
            custom_variables=recipient_in.custom_variables,
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
                new_recipients.append(
                    CampaignRecipient(
                        campaign_id=campaign_id,
                        email=norm_email,
                        first_name=item.first_name,
                        last_name=item.last_name,
                        custom_variables=item.custom_variables,
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
