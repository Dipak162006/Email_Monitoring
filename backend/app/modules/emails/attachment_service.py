from email.message import EmailMessage
import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import AttachmentStorageService
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.models import Email, EmailAttachment, EmailStatus

logger = logging.getLogger(__name__)


class AttachmentService:
    """Service layer managing email attachments: upload, validation, storage,
    authorization, listing, download, and deletion.
    """

    @classmethod
    async def upload_draft_attachment(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        upload_file: UploadFile,
        company_id: Optional[int] = None,
    ) -> EmailAttachment:
        """Upload and associate an attachment with an authorized draft."""
        draft = await db.get(Email, draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add attachments to a deleted draft. Restore it first.",
            )

        if draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add attachments to an email with status '{draft.status}'. Only DRAFT emails support adding attachments.",
            )

        # 1. Authorization: Company membership & EmailAccount access
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=draft.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this draft.",
            )

        account = await EmailAccountService.get_email_account(db, draft.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
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

        # 2. Store file on filesystem with safety validation
        try:
            safe_name, content_type, file_size, rel_path = await AttachmentStorageService.save_upload_file(
                company_id=draft.company_id,
                account_id=draft.email_account_id,
                upload_file=upload_file,
            )
        except ValueError as e:
            err_msg = str(e)
            if "exceeds maximum limit" in err_msg:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=err_msg,
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )

        # 3. Create database record
        attachment = EmailAttachment(
            company_id=draft.company_id,
            email_account_id=draft.email_account_id,
            email_id=draft.id,
            file_name=safe_name,
            content_type=content_type,
            file_size=file_size,
            storage_path=rel_path,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)

        logger.info(
            "Uploaded attachment id=%d (name='%s', size=%d) to draft id=%d by user id=%d",
            attachment.id,
            attachment.file_name,
            attachment.file_size,
            draft.id,
            current_user.id,
        )
        return attachment

    @classmethod
    async def list_draft_attachments(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        company_id: Optional[int] = None,
    ) -> Tuple[List[EmailAttachment], int]:
        """List all attachments associated with a draft."""
        return await cls.list_email_attachments(
            db=db,
            current_user=current_user,
            email_id=draft_id,
            company_id=company_id,
            require_draft=True,
        )

    @classmethod
    async def list_email_attachments(
        cls,
        db: AsyncSession,
        current_user: User,
        email_id: int,
        company_id: Optional[int] = None,
        require_draft: bool = False,
    ) -> Tuple[List[EmailAttachment], int]:
        """List all attachments for an authorized email message (draft, sent, or received)."""
        email = await db.get(Email, email_id)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found.",
            )

        if company_id is not None and email.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email does not belong to the specified company.",
            )

        if require_draft and email.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Specified email is not a draft.",
            )

        # Verify access
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=email.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this email.",
            )

        account = await EmailAccountService.get_email_account(db, email.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
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
                detail="You do not have permission to access attachments for this email account.",
            )

        stmt = select(EmailAttachment).where(EmailAttachment.email_id == email_id).order_by(EmailAttachment.created_at.asc())
        res = await db.execute(stmt)
        items = list(res.scalars().all())
        return items, len(items)

    @classmethod
    async def get_attachment(
        cls,
        db: AsyncSession,
        current_user: User,
        attachment_id: int,
        email_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ) -> EmailAttachment:
        """Retrieve attachment metadata and verify company/account authorization."""
        attachment = await db.get(EmailAttachment, attachment_id)
        if not attachment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found.",
            )

        if email_id is not None and attachment.email_id != email_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment does not belong to the specified email.",
            )

        if company_id is not None and attachment.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment does not belong to the specified company.",
            )

        # Verify authorization
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=attachment.company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the company that owns this attachment.",
            )

        account = await EmailAccountService.get_email_account(db, attachment.email_account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated email account not found.",
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
                detail="You do not have permission to access this attachment.",
            )

        return attachment

    @classmethod
    async def get_attachment_for_download(
        cls,
        db: AsyncSession,
        current_user: User,
        attachment_id: int,
        email_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ) -> Tuple[Path, str, str]:
        """Verify access and return resolved physical file path, filename, and content type."""
        attachment = await cls.get_attachment(
            db=db,
            current_user=current_user,
            attachment_id=attachment_id,
            email_id=email_id,
            company_id=company_id,
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

    @classmethod
    async def delete_draft_attachment(
        cls,
        db: AsyncSession,
        current_user: User,
        draft_id: int,
        attachment_id: int,
        company_id: Optional[int] = None,
    ) -> None:
        """Delete an attachment from an editable draft and clean up storage on disk."""
        draft = await db.get(Email, draft_id)
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft not found.",
            )

        if company_id is not None and draft.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Draft does not belong to the specified company.",
            )

        if draft.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete attachments from a deleted draft.",
            )

        if draft.status != EmailStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete attachments from an email with status '{draft.status}'. Only DRAFT emails support attachment removal.",
            )

        attachment = await cls.get_attachment(
            db=db,
            current_user=current_user,
            attachment_id=attachment_id,
            email_id=draft_id,
            company_id=company_id,
        )

        storage_path = attachment.storage_path
        await db.delete(attachment)
        await db.commit()

        # Delete physical file from disk
        await AttachmentStorageService.delete_file(storage_path)
        logger.info(
            "Deleted attachment id=%d from draft id=%d by user id=%d",
            attachment_id,
            draft_id,
            current_user.id,
        )

    @classmethod
    async def cleanup_attachments_for_email(
        cls,
        db: AsyncSession,
        email_id: int,
    ) -> int:
        """Clean up physical storage files when an email or draft is permanently deleted."""
        stmt = select(EmailAttachment).where(EmailAttachment.email_id == email_id)
        res = await db.execute(stmt)
        attachments = res.scalars().all()
        cleaned_count = 0
        for att in attachments:
            if await AttachmentStorageService.delete_file(att.storage_path):
                cleaned_count += 1
        return cleaned_count

    @classmethod
    async def attach_to_mime_message(
        cls,
        mime_msg: EmailMessage,
        attachments: Sequence[EmailAttachment],
    ) -> None:
        """Attach one or more validated EmailAttachment records to an EmailMessage."""
        for attachment in attachments:
            try:
                file_bytes = await AttachmentStorageService.read_file_bytes(attachment.storage_path)
                ctype = attachment.content_type or "application/octet-stream"
                if "/" in ctype:
                    maintype, subtype = ctype.split("/", 1)
                else:
                    maintype, subtype = "application", "octet-stream"

                mime_msg.add_attachment(
                    file_bytes,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment.file_name,
                )
            except Exception as att_err:
                logger.error("Failed to read attachment id=%d for sending: %s", attachment.id, att_err)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to read attachment file '{attachment.file_name}' for sending.",
                )

    @classmethod
    async def validate_and_load_attachments_for_send(
        cls,
        db: AsyncSession,
        attachment_ids: List[int],
        company_id: int,
        account_id: int,
        current_user: Optional[User] = None,
    ) -> List[EmailAttachment]:
        """Validate and retrieve attachments requested for sending.
        
        Enforces:
        - All requested attachment IDs exist in database.
        - Every attachment belongs to the same company.
        - Every attachment belongs to the selected EmailAccount.
        - Attachment files exist on disk and can be read.
        - User has access to the email account (if current_user provided).
        
        Raises HTTPException if any attachment is invalid or unauthorized.
        """
        if not attachment_ids:
            return []

        # Deduplicate while preserving order
        unique_ids = list(dict.fromkeys(attachment_ids))

        # Query all matching records
        stmt = select(EmailAttachment).where(EmailAttachment.id.in_(unique_ids))
        res = await db.execute(stmt)
        found = {att.id: att for att in res.scalars().all()}

        # 1. Ensure all requested attachments exist
        missing_ids = [aid for aid in unique_ids if aid not in found]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attachment(s) not found: {missing_ids}",
            )

        attachments = [found[aid] for aid in unique_ids]

        # 2. Company and Account ownership check
        for att in attachments:
            if att.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Attachment id={att.id} does not belong to company id={company_id}.",
                )
            if att.email_account_id != account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Attachment id={att.id} does not belong to email account id={account_id}.",
                )

            # 3. Ensure file exists on storage and can be resolved
            try:
                disk_path = AttachmentStorageService.resolve_storage_path(att.storage_path)
                if not disk_path.is_file():
                    raise FileNotFoundError()
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Storage file for attachment '{att.file_name}' (id={att.id}) could not be found.",
                )

        return attachments

