import csv
import io
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campaigns.schemas import normalize_and_validate_email
from app.modules.recipient_lists.models import RecipientList, RecipientListMember
from app.modules.recipient_lists.schemas import (
    RecipientListCreate,
    RecipientListImportResponse,
    RecipientListMemberCreate,
    RecipientListMemberResponse,
    RecipientListMemberUpdate,
    RecipientListResponse,
    RecipientListUpdate,
)

MAX_CSV_BYTES = 5 * 1024 * 1024  # 5MB limit for CSV uploads


class RecipientListService:
    """Service handling multi-tenant CRUD and operations for reusable Recipient Lists and Members."""

    # -----------------------------------------------------------------------
    # Recipient List Operations
    # -----------------------------------------------------------------------

    @staticmethod
    async def create_list(
        db: AsyncSession,
        company_id: int,
        list_in: RecipientListCreate,
        user_id: Optional[int] = None,
    ) -> RecipientListResponse:
        """Create a new recipient list for a company."""
        # Check uniqueness within company
        stmt = select(RecipientList.id).where(
            RecipientList.company_id == company_id,
            RecipientList.name == list_in.name,
        )
        existing = await db.scalar(stmt)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recipient list with name '{list_in.name}' already exists in this company",
            )

        new_list = RecipientList(
            company_id=company_id,
            name=list_in.name,
            description=list_in.description,
            created_by_user_id=user_id,
        )
        db.add(new_list)
        try:
            await db.commit()
            await db.refresh(new_list)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recipient list with name '{list_in.name}' already exists in this company",
            )

        return RecipientListResponse(
            id=new_list.id,
            company_id=new_list.company_id,
            name=new_list.name,
            description=new_list.description,
            created_by_user_id=new_list.created_by_user_id,
            recipient_count=0,
            created_at=new_list.created_at,
            updated_at=new_list.updated_at,
        )

    @staticmethod
    async def list_lists(
        db: AsyncSession,
        company_id: int,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[RecipientListResponse], int]:
        """List all recipient lists belonging to the company with search and member count."""
        count_subquery = (
            select(func.count(RecipientListMember.id))
            .where(RecipientListMember.list_id == RecipientList.id)
            .correlate(RecipientList)
            .scalar_subquery()
        )

        base_query = select(RecipientList, count_subquery.label("recipient_count")).where(
            RecipientList.company_id == company_id
        )

        total_query = select(func.count(RecipientList.id)).where(
            RecipientList.company_id == company_id
        )

        if search and search.strip():
            term = f"%{search.strip()}%"
            search_clause = or_(
                RecipientList.name.ilike(term),
                RecipientList.description.ilike(term),
            )
            base_query = base_query.where(search_clause)
            total_query = total_query.where(search_clause)

        total = await db.scalar(total_query) or 0

        stmt = (
            base_query.order_by(RecipientList.created_at.desc(), RecipientList.id.desc())
            .offset(offset)
            .limit(limit)
        )
        results = await db.execute(stmt)
        rows = results.all()

        items = [
            RecipientListResponse(
                id=rec_list.id,
                company_id=rec_list.company_id,
                name=rec_list.name,
                description=rec_list.description,
                created_by_user_id=rec_list.created_by_user_id,
                recipient_count=rec_count or 0,
                created_at=rec_list.created_at,
                updated_at=rec_list.updated_at,
            )
            for rec_list, rec_count in rows
        ]
        return items, total

    @staticmethod
    async def get_list(
        db: AsyncSession,
        company_id: int,
        list_id: int,
    ) -> RecipientListResponse:
        """Retrieve a specific recipient list ensuring company isolation."""
        count_subquery = (
            select(func.count(RecipientListMember.id))
            .where(RecipientListMember.list_id == RecipientList.id)
            .correlate(RecipientList)
            .scalar_subquery()
        )

        stmt = select(RecipientList, count_subquery.label("recipient_count")).where(
            RecipientList.id == list_id,
            RecipientList.company_id == company_id,
        )
        result = (await db.execute(stmt)).first()
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list not found",
            )

        rec_list, rec_count = result
        return RecipientListResponse(
            id=rec_list.id,
            company_id=rec_list.company_id,
            name=rec_list.name,
            description=rec_list.description,
            created_by_user_id=rec_list.created_by_user_id,
            recipient_count=rec_count or 0,
            created_at=rec_list.created_at,
            updated_at=rec_list.updated_at,
        )

    @staticmethod
    async def update_list(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        list_in: RecipientListUpdate,
    ) -> RecipientListResponse:
        """Update recipient list details with company isolation."""
        stmt = select(RecipientList).where(
            RecipientList.id == list_id,
            RecipientList.company_id == company_id,
        )
        rec_list = await db.scalar(stmt)
        if not rec_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list not found",
            )

        if list_in.name is not None and list_in.name != rec_list.name:
            # Check for uniqueness within company
            stmt_dup = select(RecipientList.id).where(
                RecipientList.company_id == company_id,
                RecipientList.name == list_in.name,
                RecipientList.id != list_id,
            )
            existing = await db.scalar(stmt_dup)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Recipient list with name '{list_in.name}' already exists in this company",
                )
            rec_list.name = list_in.name

        if list_in.description is not None:
            rec_list.description = list_in.description

        try:
            await db.commit()
            await db.refresh(rec_list)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recipient list with name '{list_in.name}' already exists in this company",
            )

        count_stmt = select(func.count(RecipientListMember.id)).where(
            RecipientListMember.list_id == rec_list.id
        )
        rec_count = await db.scalar(count_stmt) or 0

        return RecipientListResponse(
            id=rec_list.id,
            company_id=rec_list.company_id,
            name=rec_list.name,
            description=rec_list.description,
            created_by_user_id=rec_list.created_by_user_id,
            recipient_count=rec_count,
            created_at=rec_list.created_at,
            updated_at=rec_list.updated_at,
        )

    @staticmethod
    async def delete_list(
        db: AsyncSession,
        company_id: int,
        list_id: int,
    ) -> None:
        """Delete a recipient list and its members with company isolation.
        
        Does not affect campaign recipients or outreach history.
        """
        stmt = select(RecipientList).where(
            RecipientList.id == list_id,
            RecipientList.company_id == company_id,
        )
        rec_list = await db.scalar(stmt)
        if not rec_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list not found",
            )

        await db.delete(rec_list)
        await db.commit()

    # -----------------------------------------------------------------------
    # Member Operations
    # -----------------------------------------------------------------------

    @staticmethod
    async def _verify_list_ownership(
        db: AsyncSession,
        company_id: int,
        list_id: int,
    ) -> RecipientList:
        """Helper to verify that the list exists and belongs to the given company."""
        stmt = select(RecipientList).where(
            RecipientList.id == list_id,
            RecipientList.company_id == company_id,
        )
        rec_list = await db.scalar(stmt)
        if not rec_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list not found",
            )
        return rec_list

    @staticmethod
    async def add_member(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        member_in: RecipientListMemberCreate,
    ) -> RecipientListMemberResponse:
        """Add a contact member to a recipient list."""
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

        # Check duplicate email in this list
        stmt_dup = select(RecipientListMember.id).where(
            RecipientListMember.list_id == list_id,
            RecipientListMember.email == member_in.email,
        )
        existing = await db.scalar(stmt_dup)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Member with email '{member_in.email}' already exists in this recipient list",
            )

        member = RecipientListMember(
            list_id=list_id,
            email=member_in.email,
            first_name=member_in.first_name,
            last_name=member_in.last_name,
        )
        db.add(member)
        try:
            await db.commit()
            await db.refresh(member)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Member with email '{member_in.email}' already exists in this recipient list",
            )

        return RecipientListMemberResponse.model_validate(member)

    @staticmethod
    async def list_members(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[RecipientListMemberResponse], int]:
        """List members of a recipient list with optional search and pagination."""
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

        base_query = select(RecipientListMember).where(
            RecipientListMember.list_id == list_id
        )
        total_query = select(func.count(RecipientListMember.id)).where(
            RecipientListMember.list_id == list_id
        )

        if search and search.strip():
            term = f"%{search.strip()}%"
            search_clause = or_(
                RecipientListMember.email.ilike(term),
                RecipientListMember.first_name.ilike(term),
                RecipientListMember.last_name.ilike(term),
            )
            base_query = base_query.where(search_clause)
            total_query = total_query.where(search_clause)

        total = await db.scalar(total_query) or 0

        stmt = (
            base_query.order_by(RecipientListMember.created_at.desc(), RecipientListMember.id.desc())
            .offset(offset)
            .limit(limit)
        )
        members = (await db.scalars(stmt)).all()

        items = [RecipientListMemberResponse.model_validate(m) for m in members]
        return items, total

    @staticmethod
    async def get_member(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        member_id: int,
    ) -> RecipientListMemberResponse:
        """Retrieve a specific member of a list."""
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

        stmt = select(RecipientListMember).where(
            RecipientListMember.id == member_id,
            RecipientListMember.list_id == list_id,
        )
        member = await db.scalar(stmt)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list member not found",
            )
        return RecipientListMemberResponse.model_validate(member)

    @staticmethod
    async def update_member(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        member_id: int,
        member_in: RecipientListMemberUpdate,
    ) -> RecipientListMemberResponse:
        """Update an existing member contact."""
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

        stmt = select(RecipientListMember).where(
            RecipientListMember.id == member_id,
            RecipientListMember.list_id == list_id,
        )
        member = await db.scalar(stmt)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list member not found",
            )

        if member_in.email is not None and member_in.email != member.email:
            # Check duplicate email within this list
            stmt_dup = select(RecipientListMember.id).where(
                RecipientListMember.list_id == list_id,
                RecipientListMember.email == member_in.email,
                RecipientListMember.id != member_id,
            )
            existing = await db.scalar(stmt_dup)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Member with email '{member_in.email}' already exists in this recipient list",
                )
            member.email = member_in.email

        if member_in.first_name is not None:
            member.first_name = member_in.first_name
        if member_in.last_name is not None:
            member.last_name = member_in.last_name

        try:
            await db.commit()
            await db.refresh(member)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Member with email '{member_in.email}' already exists in this recipient list",
            )

        return RecipientListMemberResponse.model_validate(member)

    @staticmethod
    async def remove_member(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        member_id: int,
    ) -> None:
        """Remove a member contact from a list."""
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

        stmt = select(RecipientListMember).where(
            RecipientListMember.id == member_id,
            RecipientListMember.list_id == list_id,
        )
        member = await db.scalar(stmt)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient list member not found",
            )

        await db.delete(member)
        await db.commit()

    @staticmethod
    async def import_members_csv(
        db: AsyncSession,
        company_id: int,
        list_id: int,
        file: UploadFile,
    ) -> RecipientListImportResponse:
        """Import contacts from a CSV file into a recipient list.
        
        Supports ONLY email (required), first_name (optional), and last_name (optional).
        Normalizes emails, detects in-file duplicates and in-list database duplicates,
        and transactionally inserts valid contacts.
        """
        await RecipientListService._verify_list_ownership(db, company_id, list_id)

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

        seen_emails: Set[str] = set()
        candidate_rows: List[Tuple[str, Optional[str], Optional[str]]] = []
        invalid_rows: List[Dict[str, Any]] = []
        file_duplicates_count = 0
        total_data_rows = 0

        row_num = 1  # Header was row 1
        for row in reader:
            row_num += 1
            if not row or all(c.strip() == "" for c in row):
                continue  # Skip blank rows

            total_data_rows += 1

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
                file_duplicates_count += 1
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

            candidate_rows.append((norm_email, first_name, last_name))

        # 4. Check existing recipients in database for this list
        existing_in_db: Set[str] = set()
        if seen_emails:
            existing_result = await db.execute(
                select(RecipientListMember.email).where(
                    RecipientListMember.list_id == list_id,
                    RecipientListMember.email.in_(seen_emails),
                )
            )
            existing_in_db = set(existing_result.scalars().all())

        existing_duplicates_count = 0
        new_members: List[RecipientListMember] = []

        for norm_email, fn, ln in candidate_rows:
            if norm_email in existing_in_db:
                existing_duplicates_count += 1
            else:
                new_members.append(
                    RecipientListMember(
                        list_id=list_id,
                        email=norm_email,
                        first_name=fn,
                        last_name=ln,
                    )
                )

        # 5. Insert new members
        if new_members:
            db.add_all(new_members)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Database conflict occurred while inserting recipient list members",
                )

        return RecipientListImportResponse(
            total_rows=total_data_rows,
            imported_count=len(new_members),
            file_duplicates_count=file_duplicates_count,
            existing_duplicates_count=existing_duplicates_count,
            invalid_rows_count=len(invalid_rows),
            invalid_rows=invalid_rows,
        )
