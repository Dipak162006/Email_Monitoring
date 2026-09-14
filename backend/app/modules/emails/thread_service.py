import html
import re
from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.email_accounts.models import EmailAccount
from app.modules.emails.models import Email, EmailDirection, EmailThread

logger = logging.getLogger(__name__)


class EmailThreadService:
    """Service responsible for conversation thread creation, retrieval,
    RFC 2822 reply matching (In-Reply-To and References), and thread metadata maintenance.
    """

    @staticmethod
    def normalize_subject(subject: Optional[str]) -> str:
        """Strip common reply/forward prefixes (Re:, Fwd:, etc.) and tags for thread display.
        
        NOTE: Used strictly for storing and displaying the thread's subject,
        never as an automatic thread-matching mechanism.
        """
        if not subject:
            return ""
        
        cleaned = subject.strip()
        # Repeatedly strip Re: / Fwd: / Fw: prefixes and optional bracket tags like [EXT]
        pattern = re.compile(r"^\s*(?:(?:re|fwd|fw)\s*:\s*|\[[^\]]*\]\s*)", re.IGNORECASE)
        while True:
            new_cleaned = pattern.sub("", cleaned)
            if new_cleaned == cleaned:
                break
            cleaned = new_cleaned
        return cleaned.strip()

    @staticmethod
    def extract_snippet(
        body_text: Optional[str],
        body_html: Optional[str],
        max_chars: int = 150,
        max_length: Optional[int] = None,
    ) -> Optional[str]:
        """Extract a clean text preview snippet from the message body."""
        limit = max_length if max_length is not None else max_chars
        content = body_text
        if not content and body_html:
            # Strip simple HTML tags and unescape entities
            text_from_html = re.sub(r"<[^>]+>", " ", body_html)
            content = html.unescape(text_from_html)

        if not content:
            return None

        # Collapse whitespace
        snippet = " ".join(content.split())
        if len(snippet) > limit:
            return snippet[:limit].rstrip() + "..."
        return snippet


    @staticmethod
    def extract_message_ids(header_text: Optional[str]) -> List[str]:
        """Extract and deduplicate <message-id> tokens from In-Reply-To or References headers."""
        if not header_text:
            return []
        tokens = re.findall(r"<[^>]+>", header_text)
        seen = set()
        result = []
        for t in tokens:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return result

    @classmethod
    async def resolve_or_create_incoming_thread(
        cls,
        db: AsyncSession,
        account: EmailAccount,
        message_id: Optional[str],
        in_reply_to: Optional[str],
        references_header: Optional[str],
        subject: str,
        body_text: Optional[str],
        body_html: Optional[str],
        email_date: Optional[datetime],
        is_read: bool = False,
    ) -> Tuple[EmailThread, bool]:
        """Resolve an existing thread for an incoming email or create a new one.
        
        Threading Strategy:
        1. Try In-Reply-To first against existing emails in the same account/company.
        2. If no match, search References from newest to oldest ancestor.
        3. If a match is found, attach to that email's thread.
           - If the matched parent was OUTGOING, flag thread.has_reply = True.
        4. If no match is found, create a new EmailThread.
        
        Returns:
            Tuple of (EmailThread, is_reply_to_outgoing: bool)
        """
        matched_parent: Optional[Email] = None

        # 1. Try In-Reply-To primary match
        if in_reply_to:
            clean_in_reply_to = in_reply_to.strip()
            stmt = select(Email).where(
                Email.company_id == account.company_id,
                Email.email_account_id == account.id,
                Email.message_id == clean_in_reply_to,
            )
            result = await db.execute(stmt)
            matched_parent = result.scalars().first()

        # 2. Try References secondary match (newest to oldest ancestor)
        if not matched_parent and references_header:
            ref_ids = cls.extract_message_ids(references_header)
            for ref_id in reversed(ref_ids):
                stmt = select(Email).where(
                    Email.company_id == account.company_id,
                    Email.email_account_id == account.id,
                    Email.message_id == ref_id,
                )
                result = await db.execute(stmt)
                found = result.scalars().first()
                if found:
                    matched_parent = found
                    break

        # 3. If matched parent found with existing thread_id, use that thread
        if matched_parent and matched_parent.thread_id:
            thread_stmt = select(EmailThread).where(EmailThread.id == matched_parent.thread_id)
            thread_res = await db.execute(thread_stmt)
            thread = thread_res.scalars().first()
            if thread:
                is_reply_to_outgoing = (matched_parent.direction == EmailDirection.OUTGOING.value)
                return thread, is_reply_to_outgoing

        # 4. No matching thread found -> create new thread
        new_thread = EmailThread(
            company_id=account.company_id,
            email_account_id=account.id,
            subject=cls.normalize_subject(subject) or subject or "(No Subject)",
            snippet=cls.extract_snippet(body_text, body_html),
            message_count=0,  # Will be incremented when email is attached
            has_reply=False,
            last_message_at=email_date or datetime.now(timezone.utc),
            is_read=is_read,
        )
        db.add(new_thread)
        await db.flush()
        return new_thread, False

    @classmethod
    async def resolve_or_create_outgoing_thread(
        cls,
        db: AsyncSession,
        account: EmailAccount,
        requested_thread_id: Optional[int],
        in_reply_to: Optional[str],
        subject: str,
        body_text: Optional[str],
        body_html: Optional[str],
    ) -> Tuple[EmailThread, Optional[Email]]:
        """Resolve or validate the thread for an outgoing email (original or reply).
        
        Returns:
            Tuple of (EmailThread, parent_email_or_None)
        """
        # Case A: Explicit thread_id requested (replying within a thread)
        if requested_thread_id is not None:
            thread_stmt = select(EmailThread).where(EmailThread.id == requested_thread_id)
            thread_res = await db.execute(thread_stmt)
            thread = thread_res.scalars().first()
            if not thread:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation thread {requested_thread_id} not found.",
                )
            if thread.company_id != account.company_id or thread.email_account_id != account.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot reply to a thread belonging to a different email account or company.",
                )

            # Validate in_reply_to if provided
            parent_email: Optional[Email] = None
            if in_reply_to:
                p_stmt = select(Email).where(
                    Email.email_account_id == account.id,
                    Email.message_id == in_reply_to.strip(),
                    Email.thread_id == thread.id,
                )
                p_res = await db.execute(p_stmt)
                parent_email = p_res.scalars().first()
                if not parent_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Referenced in_reply_to email does not exist in the specified thread.",
                    )
            return thread, parent_email

        # Case B: in_reply_to requested without thread_id
        if in_reply_to:
            p_stmt = select(Email).where(
                Email.email_account_id == account.id,
                Email.message_id == in_reply_to.strip(),
            )
            p_res = await db.execute(p_stmt)
            parent_email = p_res.scalars().first()
            if not parent_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Referenced in_reply_to email '{in_reply_to}' not found in this account.",
                )
            if parent_email.thread_id:
                t_stmt = select(EmailThread).where(EmailThread.id == parent_email.thread_id)
                t_res = await db.execute(t_stmt)
                thread = t_res.scalars().first()
                if thread:
                    return thread, parent_email

        # Case C: New original conversation thread
        new_thread = EmailThread(
            company_id=account.company_id,
            email_account_id=account.id,
            subject=cls.normalize_subject(subject) or subject or "(No Subject)",
            snippet=cls.extract_snippet(body_text, body_html),
            message_count=0,
            has_reply=False,
            last_message_at=datetime.now(timezone.utc),
            is_read=True,
        )
        db.add(new_thread)
        await db.flush()
        return new_thread, None

    @classmethod
    def attach_email_to_thread(
        cls,
        thread: EmailThread,
        email: Email,
        is_reply_to_outgoing: bool = False,
    ) -> None:
        """Link an email to a thread and update aggregated thread metadata."""
        email.thread_id = thread.id
        thread.message_count += 1

        email_timestamp = email.sent_at or email.received_at or email.created_at or datetime.now(timezone.utc)
        if thread.last_message_at is None or email_timestamp > thread.last_message_at:
            thread.last_message_at = email_timestamp

        snippet = cls.extract_snippet(email.body_text, email.body_html)
        if snippet:
            thread.snippet = snippet

        # Update read status: if any incoming message is unread, thread is unread
        if email.direction == EmailDirection.INCOMING.value and not email.is_read:
            thread.is_read = False

        if is_reply_to_outgoing:
            thread.has_reply = True

    @classmethod
    async def list_threads(
        cls,
        db: AsyncSession,
        company_id: Optional[int] = None,
        company_ids: Optional[List[int]] = None,
        email_account_id: Optional[int] = None,
        email_account_ids: Optional[List[int]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[EmailThread], int]:
        """List conversation threads sorted by last_message_at DESC with pagination."""
        query = select(EmailThread)
        count_query = select(func.count(EmailThread.id))

        if company_id is not None:
            query = query.where(EmailThread.company_id == company_id)
            count_query = count_query.where(EmailThread.company_id == company_id)
        elif company_ids is not None:
            if not company_ids:
                return [], 0
            query = query.where(EmailThread.company_id.in_(company_ids))
            count_query = count_query.where(EmailThread.company_id.in_(company_ids))
        elif email_account_id is not None or email_account_ids is not None:
            pass  # Scoped via authorized email accounts
        else:
            return [], 0


        if email_account_id is not None:
            query = query.where(EmailThread.email_account_id == email_account_id)
            count_query = count_query.where(EmailThread.email_account_id == email_account_id)
        elif email_account_ids is not None:
            if not email_account_ids:
                return [], 0
            query = query.where(EmailThread.email_account_id.in_(email_account_ids))
            count_query = count_query.where(EmailThread.email_account_id.in_(email_account_ids))

        total_res = await db.execute(count_query)
        total_count = total_res.scalar() or 0

        query = query.order_by(EmailThread.last_message_at.desc()).offset(offset).limit(limit)
        threads_res = await db.execute(query)
        threads = threads_res.scalars().all()

        return list(threads), total_count

    @classmethod
    async def get_thread_with_emails(
        cls,
        db: AsyncSession,
        thread_id: int,
        company_id: Optional[int] = None,
    ) -> Optional[EmailThread]:
        """Retrieve a thread by ID including all its emails ordered chronologically."""
        query = (
            select(EmailThread)
            .where(EmailThread.id == thread_id)
            .options(selectinload(EmailThread.emails))
        )
        if company_id is not None:
            query = query.where(EmailThread.company_id == company_id)
        res = await db.execute(query)
        thread = res.scalars().first()
        return thread

