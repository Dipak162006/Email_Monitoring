from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.emails.models import Email, EmailAttachment, EmailDirection, EmailStatus, EmailThread
from app.modules.emails.schemas import VALID_FOLDERS

logger = logging.getLogger(__name__)


class EmailMailboxService:
    """Service handling mailbox queries (folders, raw filters, sorting, pagination)
    and email lifecycle operations (read state, star state, soft delete, restore, permanent delete).
    """

    @classmethod
    async def list_emails(
        cls,
        db: AsyncSession,
        company_id: Optional[int] = None,
        company_ids: Optional[List[int]] = None,
        email_account_id: Optional[int] = None,
        email_account_ids: Optional[List[int]] = None,
        folder: Optional[str] = None,
        status: Optional[str] = None,
        direction: Optional[str] = None,
        is_read: Optional[bool] = None,
        is_starred: Optional[bool] = None,
        is_deleted: Optional[bool] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Email], int, Dict[int, int]]:
        """Query emails with database-level filtering, folder shorthand, sorting, and pagination.
        
        Returns:
            Tuple of (emails, total_count, attachment_counts) where attachment_counts maps
            email_id -> number of stored EmailAttachment records for that email.
        """
        query = select(Email)
        count_query = select(func.count(Email.id))

        # 1. Authorization scoping: Email Accounts
        if email_account_id is not None:
            query = query.where(Email.email_account_id == email_account_id)
            count_query = count_query.where(Email.email_account_id == email_account_id)
        elif email_account_ids is not None:
            if not email_account_ids:
                return [], 0
            query = query.where(Email.email_account_id.in_(email_account_ids))
            count_query = count_query.where(Email.email_account_id.in_(email_account_ids))

        # 2. Authorization scoping: Companies
        if company_id is not None:
            query = query.where(Email.company_id == company_id)
            count_query = count_query.where(Email.company_id == company_id)
        elif company_ids is not None:
            if not company_ids:
                return [], 0
            query = query.where(Email.company_id.in_(company_ids))
            count_query = count_query.where(Email.company_id.in_(company_ids))
        elif email_account_id is None and email_account_ids is None:
            return [], 0

        # 3. Folder shorthand filtering
        if folder is not None:
            folder_lower = folder.strip().lower()
            if folder_lower not in VALID_FOLDERS:
                raise HTTPException(
                    status_code=500 if False else 400,
                    detail=f"Invalid folder '{folder}'. Supported folders: {', '.join(sorted(VALID_FOLDERS))}.",
                )

            if folder_lower == "inbox":
                f_cond = (
                    Email.direction == EmailDirection.INCOMING.value,
                    Email.status == EmailStatus.RECEIVED.value,
                    Email.is_deleted == False,
                )
                query = query.where(*f_cond)
                count_query = count_query.where(*f_cond)
            elif folder_lower == "sent":
                f_cond = (
                    Email.direction == EmailDirection.OUTGOING.value,
                    Email.status == EmailStatus.SENT.value,
                    Email.is_deleted == False,
                )
                query = query.where(*f_cond)
                count_query = count_query.where(*f_cond)
            elif folder_lower == "drafts":
                f_cond = (
                    Email.direction == EmailDirection.OUTGOING.value,
                    Email.status == EmailStatus.DRAFT.value,
                    Email.is_deleted == False,
                )
                query = query.where(*f_cond)
                count_query = count_query.where(*f_cond)
            elif folder_lower == "bounced":
                f_cond = (
                    Email.status == EmailStatus.BOUNCED.value,
                    Email.is_deleted == False,
                )
                query = query.where(*f_cond)
                count_query = count_query.where(*f_cond)
            elif folder_lower == "responses":
                query = query.join(EmailThread, Email.thread_id == EmailThread.id).where(
                    Email.direction == EmailDirection.INCOMING.value,
                    EmailThread.has_reply == True,
                    Email.is_deleted == False,
                )
                count_query = count_query.join(EmailThread, Email.thread_id == EmailThread.id).where(
                    Email.direction == EmailDirection.INCOMING.value,
                    EmailThread.has_reply == True,
                    Email.is_deleted == False,
                )
            elif folder_lower == "trash":
                query = query.where(Email.is_deleted == True)
                count_query = count_query.where(Email.is_deleted == True)
        else:
            # Default behavior when no folder is specified
            if is_deleted is not None:
                query = query.where(Email.is_deleted == is_deleted)
                count_query = count_query.where(Email.is_deleted == is_deleted)
            else:
                query = query.where(Email.is_deleted == False)
                count_query = count_query.where(Email.is_deleted == False)

        # 4. Raw Filters (AND semantics)
        if status is not None:
            query = query.where(Email.status == status)
            count_query = count_query.where(Email.status == status)

        if direction is not None:
            query = query.where(Email.direction == direction)
            count_query = count_query.where(Email.direction == direction)

        if is_read is not None:
            query = query.where(Email.is_read == is_read)
            count_query = count_query.where(Email.is_read == is_read)

        if is_starred is not None:
            query = query.where(Email.is_starred == is_starred)
            count_query = count_query.where(Email.is_starred == is_starred)

        if folder is not None and is_deleted is not None:
            query = query.where(Email.is_deleted == is_deleted)
            count_query = count_query.where(Email.is_deleted == is_deleted)

        if search and search.strip():
            term = f"%{search.strip()}%"
            search_cond = or_(
                Email.subject.ilike(term),
                Email.sender.ilike(term),
            )
            query = query.where(search_cond)
            count_query = count_query.where(search_cond)

        effective_ts = func.coalesce(Email.received_at, Email.sent_at, Email.created_at)

        if date_from is not None:
            query = query.where(effective_ts >= date_from)
            count_query = count_query.where(effective_ts >= date_from)

        if date_to is not None:
            query = query.where(effective_ts <= date_to)
            count_query = count_query.where(effective_ts <= date_to)

        # 5. Count query execution
        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        # 6. Sorting & Pagination
        if sort == "oldest":
            query = query.order_by(effective_ts.asc(), Email.id.asc())
        else:
            query = query.order_by(effective_ts.desc(), Email.id.desc())

        query = query.offset(offset).limit(limit)
        emails_res = await db.execute(query)
        emails = list(emails_res.scalars().all())

        # 7. Bulk attachment count: single query for all returned email IDs
        attachment_counts: Dict[int, int] = {}
        if emails:
            email_ids = [e.id for e in emails]
            att_count_stmt = (
                select(EmailAttachment.email_id, func.count(EmailAttachment.id).label("cnt"))
                .where(EmailAttachment.email_id.in_(email_ids))
                .group_by(EmailAttachment.email_id)
            )
            att_res = await db.execute(att_count_stmt)
            for row in att_res.all():
                attachment_counts[row.email_id] = row.cnt

        return emails, total, attachment_counts

    @classmethod
    async def recalculate_thread_read_state(cls, db: AsyncSession, thread_id: int) -> None:
        """Fully recalculate EmailThread.is_read based on active emails in the thread."""
        thread = await db.get(EmailThread, thread_id)
        if not thread:
            return

        unread_stmt = select(Email.id).where(
            Email.thread_id == thread_id,
            Email.is_read == False,
            Email.is_deleted == False,
        )
        res = await db.execute(unread_stmt)
        has_unread = res.first() is not None
        thread.is_read = not has_unread

    @classmethod
    async def mark_email_read(cls, db: AsyncSession, email: Email, is_read: bool) -> Email:
        """Update email's read state and recalculate parent conversation thread's is_read."""
        email.is_read = is_read
        await db.flush()

        if email.thread_id:
            await cls.recalculate_thread_read_state(db, email.thread_id)

        await db.commit()
        await db.refresh(email)
        return email

    @classmethod
    async def mark_email_starred(cls, db: AsyncSession, email: Email, is_starred: bool) -> Email:
        """Update email's starred state."""
        email.is_starred = is_starred
        await db.commit()
        await db.refresh(email)
        return email

    @classmethod
    async def soft_delete_email(cls, db: AsyncSession, email: Email) -> Email:
        """Soft-delete an email message into Trash."""
        email.is_deleted = True
        email.deleted_at = datetime.now(timezone.utc)
        await db.flush()

        if email.thread_id:
            await cls.recalculate_thread_read_state(db, email.thread_id)

        await db.commit()
        await db.refresh(email)
        return email

    @classmethod
    async def restore_email(cls, db: AsyncSession, email: Email) -> Email:
        """Restore a soft-deleted email message from Trash."""
        if not email.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is not in trash.",
            )

        email.is_deleted = False
        email.deleted_at = None
        await db.flush()

        if email.thread_id:
            await cls.recalculate_thread_read_state(db, email.thread_id)

        await db.commit()
        await db.refresh(email)
        return email

    @classmethod
    async def permanent_delete_email(cls, db: AsyncSession, email: Email) -> None:
        """Permanently delete an email message from the database.
        
        Only allows permanent deletion if the email is already soft-deleted in Trash.
        """
        if not email.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is not in trash. Only emails in trash can be permanently deleted.",
            )

        email_id = email.id
        from app.modules.emails.attachment_service import AttachmentService
        candidate_paths = await AttachmentService.get_email_attachment_paths(db, email_id)

        thread_id = email.thread_id
        await db.delete(email)
        await db.flush()

        if thread_id:
            count_stmt = select(func.count(Email.id)).where(Email.thread_id == thread_id)
            count_res = await db.execute(count_stmt)
            remaining = count_res.scalar() or 0

            thread = await db.get(EmailThread, thread_id)
            if thread:
                if remaining == 0:
                    await db.delete(thread)
                else:
                    thread.message_count = remaining
                    await cls.recalculate_thread_read_state(db, thread_id)

        await db.commit()

        # Clean up physical files on disk only after database deletion succeeds
        await AttachmentService.cleanup_unreferenced_storage_paths(db, candidate_paths)

    @classmethod
    async def get_mailbox_counts(
        cls,
        db: AsyncSession,
        company_id: Optional[int] = None,
        company_ids: Optional[List[int]] = None,
        email_account_id: Optional[int] = None,
        email_account_ids: Optional[List[int]] = None,
    ) -> dict:
        """Calculate exact live email counts across all mailbox folders and unread telemetry."""
        # 1. Base scoping conditions
        acc_cond = None
        if email_account_id is not None:
            acc_cond = (Email.email_account_id == email_account_id)
        elif email_account_ids is not None:
            if not email_account_ids:
                return {"inbox": 0, "unread": 0, "sent": 0, "drafts": 0, "responses": 0, "bounced": 0, "trash": 0}
            acc_cond = (Email.email_account_id.in_(email_account_ids))

        comp_cond = None
        if company_id is not None:
            comp_cond = (Email.company_id == company_id)
        elif company_ids is not None:
            if not company_ids:
                return {"inbox": 0, "unread": 0, "sent": 0, "drafts": 0, "responses": 0, "bounced": 0, "trash": 0}
            comp_cond = (Email.company_id.in_(company_ids))
        elif email_account_id is None and email_account_ids is None:
            return {"inbox": 0, "unread": 0, "sent": 0, "drafts": 0, "responses": 0, "bounced": 0, "trash": 0}

        base_conds = []
        if acc_cond is not None:
            base_conds.append(acc_cond)
        if comp_cond is not None:
            base_conds.append(comp_cond)

        # Primary query using conditional aggregation
        stmt = select(
            func.count(case((and_(Email.direction == EmailDirection.INCOMING.value, Email.status == EmailStatus.RECEIVED.value, Email.is_deleted == False), Email.id))),
            func.count(case((and_(Email.direction == EmailDirection.INCOMING.value, Email.status == EmailStatus.RECEIVED.value, Email.is_read == False, Email.is_deleted == False), Email.id))),
            func.count(case((and_(Email.direction == EmailDirection.OUTGOING.value, Email.status == EmailStatus.SENT.value, Email.is_deleted == False), Email.id))),
            func.count(case((and_(Email.direction == EmailDirection.OUTGOING.value, Email.status == EmailStatus.DRAFT.value, Email.is_deleted == False), Email.id))),
            func.count(case((and_(Email.status == EmailStatus.BOUNCED.value, Email.is_deleted == False), Email.id))),
            func.count(case((Email.is_deleted == True, Email.id))),
        )
        if base_conds:
            stmt = stmt.where(*base_conds)

        res = await db.execute(stmt)
        inbox, unread, sent, drafts, bounced, trash = res.one()

        # Responses query (joined with EmailThread)
        resp_stmt = (
            select(func.count(Email.id))
            .join(EmailThread, Email.thread_id == EmailThread.id)
            .where(
                Email.direction == EmailDirection.INCOMING.value,
                EmailThread.has_reply == True,
                Email.is_deleted == False,
            )
        )
        if base_conds:
            resp_stmt = resp_stmt.where(*base_conds)

        resp_res = await db.execute(resp_stmt)
        responses = resp_res.scalar() or 0

        return {
            "inbox": inbox or 0,
            "unread": unread or 0,
            "sent": sent or 0,
            "drafts": drafts or 0,
            "responses": responses or 0,
            "bounced": bounced or 0,
            "trash": trash or 0,
        }

