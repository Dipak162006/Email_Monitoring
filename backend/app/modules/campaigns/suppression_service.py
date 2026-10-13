from typing import List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.models import (
    CampaignRecipient,
    SuppressionEntry,
    SuppressionReason,
)
from app.modules.campaigns.schemas import (
    SuppressionBulkCreateRequest,
    SuppressionBulkCreateResponse,
    SuppressionCreate,
    SuppressionRead,
    normalize_and_validate_email,
)


class SuppressionService:
    """Service layer managing company-level suppression entries, normalization, deduplication, and lookup."""

    @staticmethod
    async def create_suppression(
        db: AsyncSession,
        company_id: int,
        suppression_in: SuppressionCreate,
    ) -> SuppressionEntry:
        """Create a single company-scoped suppression entry.
        
        Normalizes email and enforces company uniqueness constraint.
        Returns 409 Conflict if the email is already suppressed for the company.
        """
        norm_email = normalize_and_validate_email(suppression_in.email)

        # Application-level uniqueness check
        existing = await db.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.company_id == company_id,
                SuppressionEntry.email == norm_email,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{norm_email}' is already suppressed for this company.",
            )

        entry = SuppressionEntry(
            company_id=company_id,
            email=norm_email,
            reason=suppression_in.reason.value,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def list_suppressions(
        db: AsyncSession,
        company_id: int,
        reason: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SuppressionEntry]:
        """List suppression entries for a company with pagination, search, and reason filtering.
        
        Strictly company-isolated; stable descending ordering.
        """
        query = select(SuppressionEntry).where(SuppressionEntry.company_id == company_id)

        if reason:
            norm_reason = reason.strip().upper()
            query = query.where(SuppressionEntry.reason == norm_reason)

        if search:
            query = query.where(SuppressionEntry.email.ilike(f"%{search.strip().lower()}%"))

        query = query.order_by(SuppressionEntry.created_at.desc(), SuppressionEntry.id.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_suppression(
        db: AsyncSession,
        company_id: int,
        suppression_id: int,
    ) -> SuppressionEntry:
        """Retrieve a specific suppression entry scoped to a company.
        
        Returns 404 if not found or belongs to another company (anti-enumeration).
        """
        result = await db.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.id == suppression_id,
                SuppressionEntry.company_id == company_id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suppression entry not found.",
            )
        return entry

    @staticmethod
    async def delete_suppression(
        db: AsyncSession,
        company_id: int,
        suppression_id: int,
    ) -> None:
        """Permanently remove an existing company suppression entry.
        
        Requires OWNER or ADMIN role. Returns 404 for cross-company access.
        """
        entry = await SuppressionService.get_suppression(db, company_id, suppression_id)
        await db.delete(entry)
        await db.commit()

    @staticmethod
    async def bulk_create_suppressions(
        db: AsyncSession,
        company_id: int,
        bulk_in: SuppressionBulkCreateRequest,
    ) -> SuppressionBulkCreateResponse:
        """Add multiple emails to company suppression in a single transactional batch.
        
        Normalizes all addresses, deduplicates within the request, and queries existing entries
        in a single indexed query.
        """
        seen_emails: Set[str] = set()
        unique_incoming: List[str] = []
        skipped_emails: List[str] = []

        # 1. In-memory deduplication within the request batch
        for raw_email in bulk_in.emails:
            norm_email = normalize_and_validate_email(raw_email)
            if norm_email in seen_emails:
                skipped_emails.append(norm_email)
            else:
                seen_emails.add(norm_email)
                unique_incoming.append(norm_email)

        # 2. Check existing suppressions in database with a single query
        existing_in_db: Set[str] = set()
        if seen_emails:
            existing_result = await db.execute(
                select(SuppressionEntry.email).where(
                    SuppressionEntry.company_id == company_id,
                    SuppressionEntry.email.in_(seen_emails),
                )
            )
            existing_in_db = set(existing_result.scalars().all())

        # 3. Create only new non-duplicate suppression entries
        new_entries: List[SuppressionEntry] = []
        for norm_email in unique_incoming:
            if norm_email in existing_in_db:
                skipped_emails.append(norm_email)
            else:
                new_entries.append(
                    SuppressionEntry(
                        company_id=company_id,
                        email=norm_email,
                        reason=bulk_in.reason.value,
                    )
                )

        if new_entries:
            db.add_all(new_entries)
            await db.commit()
            for e in new_entries:
                await db.refresh(e)

        return SuppressionBulkCreateResponse(
            total_submitted=len(bulk_in.emails),
            inserted_count=len(new_entries),
            skipped_count=len(skipped_emails),
            entries=[SuppressionRead.model_validate(e) for e in new_entries],
            skipped_emails=skipped_emails,
        )

    @staticmethod
    async def is_suppressed(
        db: AsyncSession,
        company_id: int,
        email: str,
    ) -> bool:
        """Check if an email address is suppressed within a company.
        
        Normalizes email using the standard C3 helper and queries the indexed unique constraint.
        Does not perform caching or mutate any records.
        """
        norm_email = normalize_and_validate_email(email)
        result = await db.execute(
            select(SuppressionEntry.id).where(
                SuppressionEntry.company_id == company_id,
                SuppressionEntry.email == norm_email,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def is_recipient_suppressed(
        db: AsyncSession,
        company_id: int,
        recipient: CampaignRecipient,
    ) -> bool:
        """Check whether a given CampaignRecipient is currently suppressed under the company.
        
        Does NOT automatically modify CampaignRecipient.status (status changes belong to C5 preflight).
        """
        return await SuppressionService.is_suppressed(
            db=db,
            company_id=company_id,
            email=recipient.email,
        )

    @staticmethod
    async def get_suppressed_emails(
        db: AsyncSession,
        company_id: int,
        emails: Set[str],
    ) -> Set[str]:
        """Query company suppression list for a set of emails in a single indexed query.
        
        Normalizes emails and returns the set of suppressed email addresses.
        """
        if not emails:
            return set()
        norm_emails: Set[str] = set()
        for e in emails:
            try:
                norm_emails.add(normalize_and_validate_email(e))
            except Exception:
                norm_emails.add(str(e).strip().lower())

        result = await db.execute(
            select(SuppressionEntry.email).where(
                SuppressionEntry.company_id == company_id,
                SuppressionEntry.email.in_(norm_emails),
            )
        )
        return set(result.scalars().all())

    @staticmethod
    async def record_bounce_suppression(
        db: AsyncSession,
        company_id: int,
        email: str,
    ) -> SuppressionEntry:
        """Idempotently add an email address to the company suppression list due to a confirmed bounce.
        
        If already suppressed for this company, returns the existing entry without error
        or duplicate row insertion. Respects company isolation and unique constraint.
        Flushes session without committing to allow caller transaction boundary control.
        """
        norm_email = normalize_and_validate_email(email)
        existing_result = await db.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.company_id == company_id,
                SuppressionEntry.email == norm_email,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

        entry = SuppressionEntry(
            company_id=company_id,
            email=norm_email,
            reason=SuppressionReason.BOUNCE.value,
        )
        db.add(entry)
        await db.flush()
        return entry
