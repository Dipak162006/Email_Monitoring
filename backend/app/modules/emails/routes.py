from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.models import CompanyRole
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.attachment_service import AttachmentService
from app.modules.emails.dependencies import (
    verify_user_can_access_account,
    verify_user_can_access_email,
    verify_user_can_send_from_account,
)
from app.modules.emails.dashboard_service import DashboardService
from app.modules.emails.draft_service import EmailDraftService
from app.modules.emails.mailbox_service import EmailMailboxService
from app.modules.emails.schemas import (
    AccountHealthResponse,
    DashboardActivityResponse,
    DashboardStatsResponse,
    EmailAttachmentListResponse,
    EmailAttachmentRead,
    EmailDraftCreate,
    EmailDraftUpdate,
    EmailListResponse,
    EmailRead,
    EmailReadUpdate,
    EmailSendRequest,
    EmailSignatureCreate,
    EmailSignatureListResponse,
    EmailSignatureRead,
    EmailSignatureUpdate,
    EmailStarUpdate,
    EmailSyncJobResponse,
    EmailSyncRequest,
    EmailSyncResult,
    MailboxCountsResponse,
    EmailTemplateActiveToggle,
    EmailTemplateCreate,
    EmailTemplateListResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
    EmailThreadDetail,
    EmailThreadRead,
    ThreadListResponse,
)
from app.modules.emails.service import EmailService
from app.modules.emails.signature_service import SignatureService
from app.modules.emails.sync_service import EmailSyncService
from app.modules.emails.template_service import EmailTemplateService
from app.modules.emails.thread_service import EmailThreadService

router = APIRouter(tags=["Emails"])



@router.post(
    "/emails/send",
    response_model=EmailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send an email through an authorized company EmailAccount",
)
async def send_email(
    send_req: EmailSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Send an outgoing email message using the authorized EmailAccount.
    
    The From address is determined strictly server-side by the selected EmailAccount.
    The user must have granted access or company admin/owner privileges.
    Credentials are encrypted at rest and never exposed in the API response.
    """
    account = await verify_user_can_send_from_account(
        db=db,
        current_user=current_user,
        account_id=send_req.email_account_id,
    )

    email_service = EmailService()
    email_record = await email_service.send_email(
        db=db,
        current_user=current_user,
        account=account,
        send_req=send_req,
    )
    return EmailRead.model_validate(email_record)


@router.post(
    "/companies/{company_id}/emails/send",
    response_model=EmailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send an email scoped to a specific company and authorized account",
)
async def send_company_email(
    company_id: int,
    send_req: EmailSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Send an outgoing email scoped to a specific company ID."""
    account = await verify_user_can_send_from_account(
        db=db,
        current_user=current_user,
        account_id=send_req.email_account_id,
        company_id=company_id,
    )

    email_service = EmailService()
    email_record = await email_service.send_email(
        db=db,
        current_user=current_user,
        account=account,
        send_req=send_req,
    )
    return EmailRead.model_validate(email_record)


# -----------------------------------------------------------------------------
# M9 Compose & Draft Management API
# -----------------------------------------------------------------------------

@router.post(
    "/emails/drafts",
    response_model=EmailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft email across authorized email accounts",
)
async def create_draft(
    draft_in: EmailDraftCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Create a new work-in-progress draft message."""
    draft = await EmailDraftService.create_draft(
        db=db,
        current_user=current_user,
        draft_in=draft_in,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/companies/{company_id}/emails/drafts",
    response_model=EmailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft email scoped to a specific company",
)
async def create_company_draft(
    company_id: int,
    draft_in: EmailDraftCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Create a new draft message scoped to a company ID."""
    draft = await EmailDraftService.create_draft(
        db=db,
        current_user=current_user,
        draft_in=draft_in,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


@router.get(
    "/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve an active draft by ID",
)
async def get_draft_by_id(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Fetch an active draft message ensuring account authorization."""
    draft = await EmailDraftService.get_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
    )
    return EmailRead.model_validate(draft)


@router.get(
    "/companies/{company_id}/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve an active draft by ID scoped to a company",
)
async def get_company_draft_by_id(
    company_id: int,
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Fetch an active draft message scoped to a company."""
    draft = await EmailDraftService.get_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


@router.put(
    "/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Update an existing draft message or autosave changes",
)
async def update_draft(
    draft_id: int,
    draft_update: EmailDraftUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Update fields of an active draft message."""
    draft = await EmailDraftService.update_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        draft_update=draft_update,
    )
    return EmailRead.model_validate(draft)


@router.put(
    "/companies/{company_id}/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Update an existing draft message scoped to a company",
)
async def update_company_draft(
    company_id: int,
    draft_id: int,
    draft_update: EmailDraftUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Update fields of a draft scoped to a specific company."""
    draft = await EmailDraftService.update_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        draft_update=draft_update,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


@router.delete(
    "/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Discard a draft message (soft-delete to Trash)",
)
async def discard_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Discard a draft by soft-deleting it to Trash."""
    draft = await EmailDraftService.discard_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
    )
    return EmailRead.model_validate(draft)


@router.delete(
    "/companies/{company_id}/emails/drafts/{draft_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Discard a draft message scoped to a company",
)
async def discard_company_draft(
    company_id: int,
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Discard a draft scoped to a company by soft-deleting it."""
    draft = await EmailDraftService.discard_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/emails/drafts/{draft_id}/send",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Validate and transmit an existing draft via SMTP",
)
async def send_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Send an existing draft message via SMTP with concurrency protection."""
    sent_email = await EmailDraftService.send_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
    )
    return EmailRead.model_validate(sent_email)


@router.post(
    "/companies/{company_id}/emails/drafts/{draft_id}/send",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Validate and transmit a draft scoped to a company via SMTP",
)
async def send_company_draft(
    company_id: int,
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Send an existing draft scoped to a company via SMTP with concurrency protection."""
    sent_email = await EmailDraftService.send_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        company_id=company_id,
    )
    return EmailRead.model_validate(sent_email)


# -----------------------------------------------------------------------------
# M8 Mailbox API
# -----------------------------------------------------------------------------

@router.get(
    "/emails",
    response_model=EmailListResponse,
    status_code=status.HTTP_200_OK,
    summary="List emails across authorized accounts with folder shorthands, filters, search, and pagination",
)
async def list_emails(
    folder: Optional[str] = Query(None, description="Folder shorthand: inbox, sent, drafts, bounced, responses, trash"),
    email_status: Optional[str] = Query(None, alias="status", description="Filter by status (e.g. SENT, RECEIVED, DRAFT, BOUNCED)"),
    direction: Optional[str] = Query(None, description="Filter by direction (INCOMING, OUTGOING)"),
    email_account_id: Optional[int] = Query(None, description="Filter by email account ID"),
    company_id: Optional[int] = Query(None, description="Filter by company ID"),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    is_starred: Optional[bool] = Query(None, description="Filter by starred status"),
    search: Optional[str] = Query(None, description="Search query matching subject or sender"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    sort: str = Query("newest", pattern="^(newest|oldest)$", description="Sort order: newest or oldest"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailListResponse:
    """Retrieve a paginated list of emails constrained by folder shorthand, raw filters, and authorization."""
    from app.modules.emails.schemas import VALID_FOLDERS

    if folder is not None:
        folder_clean = folder.strip().lower()
        if folder_clean not in VALID_FOLDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid folder '{folder}'. Supported folders: {', '.join(sorted(VALID_FOLDERS))}.",
            )

    if company_id is not None:
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the specified company.",
            )

        accessible_accs = await EmailAccountService.get_user_accessible_accounts_for_company(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            user_role=membership.role,
        )
        accessible_acc_ids = [acc.id for acc in accessible_accs]
        if not accessible_acc_ids:
            return EmailListResponse(emails=[], total=0, limit=limit, offset=offset)

        if email_account_id is not None:
            if email_account_id not in accessible_acc_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this email account.",
                )
            target_account_id = email_account_id
            target_account_ids = None
        else:
            target_account_id = None
            target_account_ids = accessible_acc_ids

        emails, total, att_counts = await EmailMailboxService.list_emails(
            db=db,
            company_id=company_id,
            email_account_id=target_account_id,
            email_account_ids=target_account_ids,
            folder=folder,
            status=email_status,
            direction=direction,
            is_read=is_read,
            is_starred=is_starred,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    else:
        # Cross-company listing for current user's authorized accounts
        if email_account_id is not None:
            account = await verify_user_can_access_account(db, current_user, email_account_id)
            emails, total, att_counts = await EmailMailboxService.list_emails(
                db=db,
                company_id=account.company_id,
                email_account_id=account.id,
                folder=folder,
                status=email_status,
                direction=direction,
                is_read=is_read,
                is_starred=is_starred,
                search=search,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            all_acc_ids: List[int] = []
            for comp, role in user_companies:
                accs = await EmailAccountService.get_user_accessible_accounts_for_company(
                    db=db,
                    company_id=comp.id,
                    user_id=current_user.id,
                    user_role=role,
                )
                all_acc_ids.extend([a.id for a in accs])

            if not all_acc_ids:
                return EmailListResponse(emails=[], total=0, limit=limit, offset=offset)

            emails, total, att_counts = await EmailMailboxService.list_emails(
                db=db,
                company_ids=[comp.id for comp, _ in user_companies],
                email_account_ids=all_acc_ids,
                folder=folder,
                status=email_status,
                direction=direction,
                is_read=is_read,
                is_starred=is_starred,
                search=search,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                limit=limit,
                offset=offset,
            )

    return EmailListResponse(
        emails=[
            EmailRead.model_validate(e).model_copy(update={"attachment_count": att_counts.get(e.id, 0)})
            for e in emails
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/emails/counts",
    response_model=MailboxCountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated live email counts across mailbox folders and unread telemetry",
)
async def get_mailbox_counts(
    company_id: Optional[int] = Query(None, description="Filter by company ID"),
    email_account_id: Optional[int] = Query(None, description="Filter by email account ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailboxCountsResponse:
    """Retrieve real-time mailbox counts (inbox, unread, sent, drafts, responses, bounced, trash)."""
    if company_id is not None:
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the specified company.",
            )

        accessible_accs = await EmailAccountService.get_user_accessible_accounts_for_company(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            user_role=membership.role,
        )
        accessible_acc_ids = [acc.id for acc in accessible_accs]
        if not accessible_acc_ids:
            return MailboxCountsResponse()

        if email_account_id is not None:
            if email_account_id not in accessible_acc_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this email account.",
                )
            target_account_id = email_account_id
            target_account_ids = None
        else:
            target_account_id = None
            target_account_ids = accessible_acc_ids

        counts = await EmailMailboxService.get_mailbox_counts(
            db=db,
            company_id=company_id,
            email_account_id=target_account_id,
            email_account_ids=target_account_ids,
        )
        return MailboxCountsResponse(**counts)
    else:
        if email_account_id is not None:
            account = await verify_user_can_access_account(db, current_user, email_account_id)
            counts = await EmailMailboxService.get_mailbox_counts(
                db=db,
                company_id=account.company_id,
                email_account_id=account.id,
            )
            return MailboxCountsResponse(**counts)
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            all_acc_ids: List[int] = []
            for comp, role in user_companies:
                accs = await EmailAccountService.get_user_accessible_accounts_for_company(
                    db=db,
                    company_id=comp.id,
                    user_id=current_user.id,
                    user_role=role,
                )
                all_acc_ids.extend([a.id for a in accs])

            if not all_acc_ids:
                return MailboxCountsResponse()

            counts = await EmailMailboxService.get_mailbox_counts(
                db=db,
                company_ids=[comp.id for comp, _ in user_companies],
                email_account_ids=all_acc_ids,
            )
            return MailboxCountsResponse(**counts)


@router.get(
    "/companies/{company_id}/emails/counts",
    response_model=MailboxCountsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated live email counts scoped to a specific company",
)
async def get_company_mailbox_counts(
    company_id: int,
    email_account_id: Optional[int] = Query(None, description="Filter by email account ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailboxCountsResponse:
    """Retrieve real-time mailbox counts strictly scoped to a specific company."""
    return await get_mailbox_counts(
        company_id=company_id,
        email_account_id=email_account_id,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/companies/{company_id}/emails",
    response_model=EmailListResponse,
    status_code=status.HTTP_200_OK,
    summary="List emails scoped strictly to a specific company",
)
async def list_company_emails(
    company_id: int,
    folder: Optional[str] = Query(None, description="Folder shorthand: inbox, sent, drafts, bounced, responses, trash"),
    email_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    direction: Optional[str] = Query(None, description="Filter by direction"),
    email_account_id: Optional[int] = Query(None, description="Filter by email account ID"),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    is_starred: Optional[bool] = Query(None, description="Filter by starred status"),
    search: Optional[str] = Query(None, description="Search query matching subject or sender"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    sort: str = Query("newest", pattern="^(newest|oldest)$", description="Sort order: newest or oldest"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailListResponse:
    """List emails scoped strictly to a specific company ID."""
    if email_account_id is not None:
        account = await EmailAccountService.get_email_account(db, email_account_id)
        if not account or account.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account does not belong to the specified company.",
            )

    return await list_emails(
        folder=folder,
        email_status=email_status,
        direction=direction,
        email_account_id=email_account_id,
        company_id=company_id,
        is_read=is_read,
        is_starred=is_starred,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/emails/{email_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Get email details by ID (must belong to authorized account)",
)
async def get_email_by_id(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Retrieve details and delivery status of an email record."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    return EmailRead.model_validate(email_record)


@router.get(
    "/companies/{company_id}/emails/{email_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Get email details scoped to a specific company",
)
async def get_company_email_by_id(
    company_id: int,
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Retrieve details of an email record scoped to a company."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    if email_record.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email does not belong to the specified company.",
        )
    return EmailRead.model_validate(email_record)


@router.patch(
    "/emails/{email_id}/read",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Explicitly set email read or unread state and recalculate thread read state",
)
async def mark_email_read_state(
    email_id: int,
    read_req: EmailReadUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Set email read/unread flag and recalculate parent conversation thread read state."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    updated_email = await EmailMailboxService.mark_email_read(
        db=db,
        email=email_record,
        is_read=read_req.is_read,
    )
    return EmailRead.model_validate(updated_email)


@router.patch(
    "/emails/{email_id}/star",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Explicitly star or unstar an email message",
)
async def mark_email_starred_state(
    email_id: int,
    star_req: EmailStarUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Set email starred/unstarred flag."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    updated_email = await EmailMailboxService.mark_email_starred(
        db=db,
        email=email_record,
        is_starred=star_req.is_starred,
    )
    return EmailRead.model_validate(updated_email)


@router.delete(
    "/emails/{email_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-delete an email message into Trash",
)
async def soft_delete_email(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Soft-delete an email message to Trash (is_deleted=True, deleted_at=now)."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    trashed_email = await EmailMailboxService.soft_delete_email(
        db=db,
        email=email_record,
    )
    return EmailRead.model_validate(trashed_email)


@router.patch(
    "/emails/{email_id}/restore",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Restore a soft-deleted email message from Trash",
)
async def restore_email(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Restore an email from Trash back to its active state."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    restored_email = await EmailMailboxService.restore_email(
        db=db,
        email=email_record,
    )
    return EmailRead.model_validate(restored_email)


@router.delete(
    "/emails/{email_id}/permanent",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete an email message from the database",
)
async def permanent_delete_email(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete an email that is already soft-deleted in Trash."""
    email_record = await verify_user_can_access_email(
        db=db,
        current_user=current_user,
        email_id=email_id,
    )
    await EmailMailboxService.permanent_delete_email(
        db=db,
        email=email_record,
    )
    return {"message": "Email permanently deleted.", "id": email_id}


@router.post(
    "/email-accounts/{account_id}/sync",
    response_model=Union[EmailSyncResult, EmailSyncJobResponse],
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand IMAP synchronization for an authorized email account",
)
async def sync_email_account(
    account_id: int,
    sync_req: Optional[EmailSyncRequest] = None,
    background: bool = Query(default=False, description="Enqueue synchronization in Celery background worker"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
) -> Union[EmailSyncResult, EmailSyncJobResponse]:
    """Synchronize incoming messages from IMAP server into local database."""
    account = await verify_user_can_access_account(
        db=db,
        current_user=current_user,
        account_id=account_id,
    )
    req = sync_req or EmailSyncRequest()
    is_background = background or req.background

    if is_background:
        from app.workers.tasks import sync_email_account_task
        task = sync_email_account_task.delay(
            account_id=account.id,
            folder=req.folder,
            max_messages=req.max_messages,
        )
        if response is not None:
            response.status_code = status.HTTP_202_ACCEPTED
        return EmailSyncJobResponse(
            task_id=task.id,
            status="QUEUED",
            email_account_id=account.id,
            folder=req.folder,
            message="Email synchronization queued in background.",
        )

    sync_service = EmailSyncService()
    return await sync_service.sync_mailbox(
        db=db,
        account=account,
        folder=req.folder,
        max_messages=req.max_messages,
    )


@router.post(
    "/companies/{company_id}/email-accounts/{account_id}/sync",
    response_model=Union[EmailSyncResult, EmailSyncJobResponse],
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand IMAP synchronization scoped to a company",
)
async def sync_company_email_account(
    company_id: int,
    account_id: int,
    sync_req: Optional[EmailSyncRequest] = None,
    background: bool = Query(default=False, description="Enqueue synchronization in Celery background worker"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
) -> Union[EmailSyncResult, EmailSyncJobResponse]:
    """Synchronize incoming messages scoped to a specific company ID."""
    account = await verify_user_can_access_account(
        db=db,
        current_user=current_user,
        account_id=account_id,
        company_id=company_id,
    )
    req = sync_req or EmailSyncRequest()
    is_background = background or req.background

    if is_background:
        from app.workers.tasks import sync_email_account_task
        task = sync_email_account_task.delay(
            account_id=account.id,
            folder=req.folder,
            max_messages=req.max_messages,
        )
        if response is not None:
            response.status_code = status.HTTP_202_ACCEPTED
        return EmailSyncJobResponse(
            task_id=task.id,
            status="QUEUED",
            email_account_id=account.id,
            folder=req.folder,
            message="Email synchronization queued in background.",
        )

    sync_service = EmailSyncService()
    return await sync_service.sync_mailbox(
        db=db,
        account=account,
        folder=req.folder,
        max_messages=req.max_messages,
    )


@router.get(
    "/email-accounts/sync-jobs/{task_id}",
    summary="Get status of a background synchronization job",
)
async def get_sync_job_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve status and result of an asynchronous background sync job."""
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    response_data: Dict[str, Any] = {
        "task_id": task_id,
        "status": result.status,
    }
    if result.ready():
        if result.successful():
            response_data["result"] = result.result
        else:
            response_data["error"] = str(result.result)
    return response_data



# -----------------------------------------------------------------------------
# Conversation Threads API (M7)
# -----------------------------------------------------------------------------

@router.get(
    "/threads",
    response_model=ThreadListResponse,
    status_code=status.HTTP_200_OK,
    summary="List conversation threads for authorized companies and accounts",
)
async def list_threads(
    company_id: Optional[int] = Query(None, description="Filter threads by company ID"),
    email_account_id: Optional[int] = Query(None, description="Filter threads by email account ID"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadListResponse:
    """List conversation threads with pagination, sorted by newest activity (last_message_at DESC)."""
    if company_id is not None:
        membership = await CompanyService.get_user_membership(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not belong to the specified company.",
            )

        accessible_accs = await EmailAccountService.get_user_accessible_accounts_for_company(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            user_role=membership.role,
        )
        accessible_acc_ids = [acc.id for acc in accessible_accs]
        if not accessible_acc_ids:
            return ThreadListResponse(threads=[], total=0, limit=limit, offset=offset)

        if email_account_id is not None:
            if email_account_id not in accessible_acc_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this email account.",
                )
            threads, total = await EmailThreadService.list_threads(
                db=db,
                company_id=company_id,
                email_account_id=email_account_id,
                limit=limit,
                offset=offset,
            )
        else:
            threads, total = await EmailThreadService.list_threads(
                db=db,
                company_id=company_id,
                email_account_ids=accessible_acc_ids,
                limit=limit,
                offset=offset,
            )
    else:
        # Cross-company listing for current user's authorized accounts
        if email_account_id is not None:
            account = await verify_user_can_access_account(db, current_user, email_account_id)
            threads, total = await EmailThreadService.list_threads(
                db=db,
                company_id=account.company_id,
                email_account_id=account.id,
                limit=limit,
                offset=offset,
            )
        else:
            user_companies = await CompanyService.get_user_companies(db, current_user.id)
            all_acc_ids: List[int] = []
            for comp, role in user_companies:
                accs = await EmailAccountService.get_user_accessible_accounts_for_company(
                    db=db,
                    company_id=comp.id,
                    user_id=current_user.id,
                    user_role=role,
                )
                all_acc_ids.extend([a.id for a in accs])

            if not all_acc_ids:
                return ThreadListResponse(threads=[], total=0, limit=limit, offset=offset)

            threads, total = await EmailThreadService.list_threads(
                db=db,
                company_ids=[comp.id for comp, _ in user_companies],
                email_account_ids=all_acc_ids,
                limit=limit,
                offset=offset,
            )


    return ThreadListResponse(
        threads=[EmailThreadRead.model_validate(t) for t in threads],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/companies/{company_id}/threads",
    response_model=ThreadListResponse,
    status_code=status.HTTP_200_OK,
    summary="List conversation threads scoped to a specific company",
)
async def list_company_threads(
    company_id: int,
    email_account_id: Optional[int] = Query(None, description="Filter threads by email account ID"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadListResponse:
    """List conversation threads scoped strictly to a specific company."""
    return await list_threads(
        company_id=company_id,
        email_account_id=email_account_id,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/threads/{thread_id}",
    response_model=EmailThreadDetail,
    status_code=status.HTTP_200_OK,
    summary="Get conversation thread details by ID with chronologically ordered emails",
)
async def get_thread_by_id(
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailThreadDetail:
    """Retrieve full details of a conversation thread including all associated messages."""
    thread = await EmailThreadService.get_thread_with_emails(db, thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation thread {thread_id} not found.",
        )

    membership = await CompanyService.get_user_membership(
        db=db,
        company_id=thread.company_id,
        user_id=current_user.id,
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation thread.",
        )

    account = await EmailAccountService.get_email_account(db, thread.email_account_id)
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
            detail="You do not have access to this conversation thread.",
        )

    return EmailThreadDetail.model_validate(thread)


@router.get(
    "/companies/{company_id}/threads/{thread_id}",
    response_model=EmailThreadDetail,
    status_code=status.HTTP_200_OK,
    summary="Get conversation thread details scoped to a company",
)
async def get_company_thread_by_id(
    company_id: int,
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailThreadDetail:
    """Retrieve conversation thread scoped to a specific company ID."""
    thread = await EmailThreadService.get_thread_with_emails(db, thread_id, company_id=company_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation thread {thread_id} not found in this company.",
        )

    return await get_thread_by_id(thread_id=thread_id, current_user=current_user, db=db)


# -----------------------------------------------------------------------------
# M10 Email Templates API
# -----------------------------------------------------------------------------

@router.post(
    "/emails/templates",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new reusable email template",
)
@router.post(
    "/templates",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_template(
    template_in: EmailTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Create a new reusable email template for authorized company and/or email account."""
    template = await EmailTemplateService.create_template(
        db=db,
        current_user=current_user,
        template_in=template_in,
    )
    return EmailTemplateRead.model_validate(template)


@router.post(
    "/companies/{company_id}/emails/templates",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new reusable email template scoped to a company",
)
@router.post(
    "/companies/{company_id}/templates",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_company_template(
    company_id: int,
    template_in: EmailTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Create a new reusable email template scoped to a specific company ID."""
    template = await EmailTemplateService.create_template(
        db=db,
        current_user=current_user,
        template_in=template_in,
        company_id=company_id,
    )
    return EmailTemplateRead.model_validate(template)


@router.get(
    "/emails/templates",
    response_model=EmailTemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List email templates available to the authorized user",
)
@router.get(
    "/templates",
    response_model=EmailTemplateListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_templates(
    company_id: Optional[int] = Query(None, description="Filter templates by company ID"),
    email_account_id: Optional[int] = Query(None, description="Filter templates by email account ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateListResponse:
    """List email templates accessible to the user with optional filters."""
    templates, total = await EmailTemplateService.list_templates(
        db=db,
        current_user=current_user,
        company_id=company_id,
        email_account_id=email_account_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return EmailTemplateListResponse(
        templates=[EmailTemplateRead.model_validate(t) for t in templates],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/companies/{company_id}/emails/templates",
    response_model=EmailTemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List email templates scoped to a specific company",
)
@router.get(
    "/companies/{company_id}/templates",
    response_model=EmailTemplateListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_company_templates(
    company_id: int,
    email_account_id: Optional[int] = Query(None, description="Filter templates by email account ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateListResponse:
    """List email templates scoped strictly to a specific company ID."""
    return await list_templates(
        company_id=company_id,
        email_account_id=email_account_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/emails/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Get an email template by ID",
)
@router.get(
    "/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_template_by_id(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Fetch an email template by ID ensuring company and account authorization."""
    template = await EmailTemplateService.get_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
    )
    return EmailTemplateRead.model_validate(template)


@router.get(
    "/companies/{company_id}/emails/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Get an email template by ID scoped to a company",
)
@router.get(
    "/companies/{company_id}/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_company_template_by_id(
    company_id: int,
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Fetch an email template by ID scoped to a company."""
    template = await EmailTemplateService.get_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
        company_id=company_id,
    )
    return EmailTemplateRead.model_validate(template)


@router.put(
    "/emails/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Update an existing email template",
)
@router.put(
    "/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_template(
    template_id: int,
    template_update: EmailTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Update fields of an existing email template."""
    template = await EmailTemplateService.update_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
        template_update=template_update,
    )
    return EmailTemplateRead.model_validate(template)


@router.put(
    "/companies/{company_id}/emails/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Update an existing email template scoped to a company",
)
@router.put(
    "/companies/{company_id}/templates/{template_id}",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_company_template(
    company_id: int,
    template_id: int,
    template_update: EmailTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Update fields of an email template scoped to a company."""
    template = await EmailTemplateService.update_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
        template_update=template_update,
        company_id=company_id,
    )
    return EmailTemplateRead.model_validate(template)


@router.delete(
    "/emails/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email template",
)
@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an email template using standard deletion."""
    await EmailTemplateService.delete_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
    )


@router.delete(
    "/companies/{company_id}/emails/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email template scoped to a company",
)
@router.delete(
    "/companies/{company_id}/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_company_template(
    company_id: int,
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an email template scoped to a specific company."""
    await EmailTemplateService.delete_template(
        db=db,
        current_user=current_user,
        template_id=template_id,
        company_id=company_id,
    )


@router.patch(
    "/emails/templates/{template_id}/active",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Toggle or update the active status of an email template",
)
@router.patch(
    "/templates/{template_id}/active",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def toggle_template_active(
    template_id: int,
    active_in: Optional[EmailTemplateActiveToggle] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Toggle or set the active status of an email template."""
    is_active = active_in.is_active if active_in is not None else None
    template = await EmailTemplateService.toggle_active(
        db=db,
        current_user=current_user,
        template_id=template_id,
        is_active=is_active,
    )
    return EmailTemplateRead.model_validate(template)


@router.patch(
    "/companies/{company_id}/emails/templates/{template_id}/active",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Toggle or update active status of a template scoped to a company",
)
@router.patch(
    "/companies/{company_id}/templates/{template_id}/active",
    response_model=EmailTemplateRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def toggle_company_template_active(
    company_id: int,
    template_id: int,
    active_in: Optional[EmailTemplateActiveToggle] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailTemplateRead:
    """Toggle or set the active status of a company-scoped email template."""
    is_active = active_in.is_active if active_in is not None else None
    template = await EmailTemplateService.toggle_active(
        db=db,
        current_user=current_user,
        template_id=template_id,
        is_active=is_active,
        company_id=company_id,
    )
    return EmailTemplateRead.model_validate(template)


# -----------------------------------------------------------------------------
# M10 Template -> Draft Integration API
# -----------------------------------------------------------------------------

@router.post(
    "/emails/drafts/{draft_id}/apply-template/{template_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply a reusable email template to an existing draft",
)
@router.post(
    "/drafts/{draft_id}/apply-template/{template_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_template_to_draft(
    draft_id: int,
    template_id: int,
    signature_id: Optional[int] = Query(default=None, description="Optional signature ID to apply after template"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply an active email template to an existing draft email.
    
    Populates subject, body_text, and body_html while preserving recipients and thread references.
    Optionally applies selected or default signature.
    """
    draft = await EmailTemplateService.apply_template_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        template_id=template_id,
        signature_id=signature_id,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/companies/{company_id}/emails/drafts/{draft_id}/apply-template/{template_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply a template to an existing draft scoped to a company",
)
@router.post(
    "/companies/{company_id}/drafts/{draft_id}/apply-template/{template_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_company_template_to_draft(
    company_id: int,
    draft_id: int,
    template_id: int,
    signature_id: Optional[int] = Query(default=None, description="Optional signature ID to apply after template"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply an active email template to an existing draft email scoped to a company."""
    draft = await EmailTemplateService.apply_template_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        template_id=template_id,
        company_id=company_id,
        signature_id=signature_id,
    )
    return EmailRead.model_validate(draft)


# -----------------------------------------------------------------------------
# M11 Email Signatures API
# -----------------------------------------------------------------------------

@router.post(
    "/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new email signature",
)
@router.post(
    "/emails/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_signature(
    signature_in: EmailSignatureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Create a new email signature for an authorized EmailAccount."""
    signature = await SignatureService.create_signature(
        db=db,
        current_user=current_user,
        signature_in=signature_in,
    )
    return EmailSignatureRead.model_validate(signature)


@router.post(
    "/email-accounts/{account_id}/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a signature scoped to an email account",
)
async def create_account_signature(
    account_id: int,
    signature_in: EmailSignatureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Create a signature directly scoped to an email account ID."""
    signature = await SignatureService.create_signature(
        db=db,
        current_user=current_user,
        signature_in=signature_in,
        account_id=account_id,
    )
    return EmailSignatureRead.model_validate(signature)


@router.post(
    "/companies/{company_id}/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a signature scoped to a company",
)
@router.post(
    "/companies/{company_id}/emails/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_company_signature(
    company_id: int,
    signature_in: EmailSignatureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Create a new email signature scoped to a specific company."""
    signature = await SignatureService.create_signature(
        db=db,
        current_user=current_user,
        signature_in=signature_in,
        company_id=company_id,
    )
    return EmailSignatureRead.model_validate(signature)


@router.post(
    "/companies/{company_id}/email-accounts/{account_id}/signatures",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a signature scoped to a company and email account",
)
async def create_company_account_signature(
    company_id: int,
    account_id: int,
    signature_in: EmailSignatureCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Create a signature scoped to both company ID and account ID."""
    signature = await SignatureService.create_signature(
        db=db,
        current_user=current_user,
        signature_in=signature_in,
        company_id=company_id,
        account_id=account_id,
    )
    return EmailSignatureRead.model_validate(signature)


@router.get(
    "/signatures",
    response_model=EmailSignatureListResponse,
    status_code=status.HTTP_200_OK,
    summary="List email signatures accessible to current user",
)
@router.get(
    "/emails/signatures",
    response_model=EmailSignatureListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_signatures(
    email_account_id: Optional[int] = Query(None, description="Filter signatures by EmailAccount ID"),
    company_id: Optional[int] = Query(None, description="Filter signatures by Company ID"),
    limit: int = Query(50, ge=1, le=100, description="Max signatures to return"),
    offset: int = Query(0, ge=0, description="Number of signatures to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureListResponse:
    """List email signatures for authorized accounts/companies."""
    signatures, total = await SignatureService.list_signatures(
        db=db,
        current_user=current_user,
        company_id=company_id,
        account_id=email_account_id,
        limit=limit,
        offset=offset,
    )
    return EmailSignatureListResponse(
        signatures=[EmailSignatureRead.model_validate(s) for s in signatures],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/email-accounts/{account_id}/signatures",
    response_model=EmailSignatureListResponse,
    status_code=status.HTTP_200_OK,
    summary="List signatures for a specific email account",
)
async def list_account_signatures(
    account_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureListResponse:
    """List signatures scoped to an email account."""
    signatures, total = await SignatureService.list_signatures(
        db=db,
        current_user=current_user,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )
    return EmailSignatureListResponse(
        signatures=[EmailSignatureRead.model_validate(s) for s in signatures],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/companies/{company_id}/signatures",
    response_model=EmailSignatureListResponse,
    status_code=status.HTTP_200_OK,
    summary="List signatures scoped to a company",
)
@router.get(
    "/companies/{company_id}/emails/signatures",
    response_model=EmailSignatureListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_company_signatures(
    company_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureListResponse:
    """List signatures scoped to a company."""
    signatures, total = await SignatureService.list_signatures(
        db=db,
        current_user=current_user,
        company_id=company_id,
        limit=limit,
        offset=offset,
    )
    return EmailSignatureListResponse(
        signatures=[EmailSignatureRead.model_validate(s) for s in signatures],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/signatures/default",
    response_model=Optional[EmailSignatureRead],
    status_code=status.HTTP_200_OK,
    summary="Get default signature for an email account",
)
async def get_default_signature(
    email_account_id: int = Query(..., description="EmailAccount ID to query default signature for"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[EmailSignatureRead]:
    """Retrieve the effective default signature for an authorized EmailAccount."""
    sig = await SignatureService.get_default_signature(
        db=db,
        current_user=current_user,
        account_id=email_account_id,
    )
    return EmailSignatureRead.model_validate(sig) if sig else None


@router.get(
    "/email-accounts/{account_id}/signatures/default",
    response_model=Optional[EmailSignatureRead],
    status_code=status.HTTP_200_OK,
    summary="Get default signature for an email account path",
)
async def get_account_default_signature(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[EmailSignatureRead]:
    """Retrieve the default signature for an email account specified by path."""
    sig = await SignatureService.get_default_signature(
        db=db,
        current_user=current_user,
        account_id=account_id,
    )
    return EmailSignatureRead.model_validate(sig) if sig else None


@router.get(
    "/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve an email signature by ID",
)
@router.get(
    "/emails/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_signature_by_id(
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Retrieve a single signature ensuring user authorization."""
    sig = await SignatureService.get_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
    )
    return EmailSignatureRead.model_validate(sig)


@router.get(
    "/companies/{company_id}/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve an email signature scoped to a company",
)
@router.get(
    "/companies/{company_id}/emails/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_company_signature_by_id(
    company_id: int,
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Retrieve a single signature scoped to a company."""
    sig = await SignatureService.get_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
        company_id=company_id,
    )
    return EmailSignatureRead.model_validate(sig)


@router.put(
    "/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Update an email signature",
)
@router.patch(
    "/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.put(
    "/emails/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_signature(
    signature_id: int,
    signature_in: EmailSignatureUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Update fields of an active email signature."""
    sig = await SignatureService.update_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
        signature_in=signature_in,
    )
    return EmailSignatureRead.model_validate(sig)


@router.put(
    "/companies/{company_id}/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Update a signature scoped to a company",
)
@router.patch(
    "/companies/{company_id}/signatures/{signature_id}",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def update_company_signature(
    company_id: int,
    signature_id: int,
    signature_in: EmailSignatureUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Update a signature scoped to a company."""
    sig = await SignatureService.update_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
        signature_in=signature_in,
        company_id=company_id,
    )
    return EmailSignatureRead.model_validate(sig)


@router.delete(
    "/signatures/{signature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email signature",
)
@router.delete(
    "/emails/signatures/{signature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_signature(
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an email signature."""
    await SignatureService.delete_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
    )


@router.delete(
    "/companies/{company_id}/signatures/{signature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email signature scoped to a company",
)
@router.delete(
    "/companies/{company_id}/emails/signatures/{signature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_company_signature(
    company_id: int,
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a signature scoped to a company."""
    await SignatureService.delete_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
        company_id=company_id,
    )


@router.post(
    "/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Set signature as default for its email account",
)
@router.put(
    "/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.patch(
    "/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.patch(
    "/signatures/{signature_id}/default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def set_default_signature(
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Set the specified signature as the default for its associated account."""
    sig = await SignatureService.set_default_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
    )
    return EmailSignatureRead.model_validate(sig)


@router.post(
    "/companies/{company_id}/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    summary="Set signature as default scoped to a company",
)
@router.put(
    "/companies/{company_id}/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.patch(
    "/companies/{company_id}/signatures/{signature_id}/set-default",
    response_model=EmailSignatureRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def set_company_default_signature(
    company_id: int,
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSignatureRead:
    """Set signature as default scoped to a company."""
    sig = await SignatureService.set_default_signature(
        db=db,
        current_user=current_user,
        signature_id=signature_id,
        company_id=company_id,
    )
    return EmailSignatureRead.model_validate(sig)


# -----------------------------------------------------------------------------
# M11 Draft Signature Application Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/emails/drafts/{draft_id}/apply-signature/{signature_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply an authorized signature to an existing draft",
)
@router.post(
    "/drafts/{draft_id}/apply-signature/{signature_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_signature_to_draft(
    draft_id: int,
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply an authorized signature to an existing draft email."""
    draft = await SignatureService.apply_signature_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        signature_id=signature_id,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/emails/drafts/{draft_id}/apply-signature",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply the default signature for the draft's account",
)
@router.post(
    "/drafts/{draft_id}/apply-signature",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_default_signature_to_draft(
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply the default signature of the draft's email account to the draft."""
    draft = await SignatureService.apply_signature_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        signature_id=None,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/companies/{company_id}/emails/drafts/{draft_id}/apply-signature/{signature_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply a signature to a draft scoped to a company",
)
@router.post(
    "/companies/{company_id}/drafts/{draft_id}/apply-signature/{signature_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_company_signature_to_draft(
    company_id: int,
    draft_id: int,
    signature_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply a signature to a draft scoped to a company."""
    draft = await SignatureService.apply_signature_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        signature_id=signature_id,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


@router.post(
    "/companies/{company_id}/emails/drafts/{draft_id}/apply-signature",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Apply default signature to a draft scoped to a company",
)
@router.post(
    "/companies/{company_id}/drafts/{draft_id}/apply-signature",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def apply_company_default_signature_to_draft(
    company_id: int,
    draft_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Apply default signature to a draft scoped to a company."""
    draft = await SignatureService.apply_signature_to_draft(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        signature_id=None,
        company_id=company_id,
    )
    return EmailRead.model_validate(draft)


# -----------------------------------------------------------------------------
# M12 Email Attachments Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/emails/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a draft email",
)
@router.post(
    "/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/companies/{company_id}/emails/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/companies/{company_id}/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_draft_attachment(
    draft_id: int,
    file: UploadFile = File(...),
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailAttachmentRead:
    """Upload a file attachment and associate it with an existing draft."""
    attachment = await AttachmentService.upload_draft_attachment(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        upload_file=file,
        company_id=company_id,
    )
    return EmailAttachmentRead.model_validate(attachment)


@router.get(
    "/emails/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all attachments associated with a draft email",
)
@router.get(
    "/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.get(
    "/companies/{company_id}/emails/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.get(
    "/companies/{company_id}/drafts/{draft_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_draft_attachments(
    draft_id: int,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailAttachmentListResponse:
    """List all attachments associated with an editable draft."""
    items, total = await AttachmentService.list_draft_attachments(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        company_id=company_id,
    )
    return EmailAttachmentListResponse(
        attachments=[EmailAttachmentRead.model_validate(i) for i in items],
        total=total,
    )


@router.delete(
    "/emails/drafts/{draft_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment from a draft email",
)
@router.delete(
    "/drafts/{draft_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
@router.delete(
    "/companies/{company_id}/emails/drafts/{draft_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
@router.delete(
    "/companies/{company_id}/drafts/{draft_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_draft_attachment(
    draft_id: int,
    attachment_id: int,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an attachment from an editable draft and delete its file from storage."""
    await AttachmentService.delete_draft_attachment(
        db=db,
        current_user=current_user,
        draft_id=draft_id,
        attachment_id=attachment_id,
        company_id=company_id,
    )


@router.get(
    "/emails/{email_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all attachments associated with an email",
)
@router.get(
    "/companies/{company_id}/emails/{email_id}/attachments",
    response_model=EmailAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_email_attachments(
    email_id: int,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailAttachmentListResponse:
    """List all attachments associated with any authorized email message."""
    items, total = await AttachmentService.list_email_attachments(
        db=db,
        current_user=current_user,
        email_id=email_id,
        company_id=company_id,
    )
    return EmailAttachmentListResponse(
        attachments=[EmailAttachmentRead.model_validate(i) for i in items],
        total=total,
    )


@router.get(
    "/emails/{email_id}/attachments/{attachment_id}",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_200_OK,
    summary="Get attachment metadata",
)
@router.get(
    "/companies/{company_id}/emails/{email_id}/attachments/{attachment_id}",
    response_model=EmailAttachmentRead,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_attachment_metadata(
    email_id: int,
    attachment_id: int,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailAttachmentRead:
    """Retrieve metadata of a specific attachment."""
    att = await AttachmentService.get_attachment(
        db=db,
        current_user=current_user,
        attachment_id=attachment_id,
        email_id=email_id,
        company_id=company_id,
    )
    return EmailAttachmentRead.model_validate(att)


@router.get(
    "/emails/{email_id}/attachments/{attachment_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download an attachment file",
)
@router.get(
    "/companies/{company_id}/emails/{email_id}/attachments/{attachment_id}/download",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.get(
    "/attachments/{attachment_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download an attachment file by attachment ID",
)
async def download_attachment_file(
    attachment_id: int,
    email_id: Optional[int] = None,
    company_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download the binary content of an authorized attachment."""
    file_path, filename, content_type = await AttachmentService.get_attachment_for_download(
        db=db,
        current_user=current_user,
        attachment_id=attachment_id,
        email_id=email_id,
        company_id=company_id,
    )
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------------------------------------------------------
# Dashboard Analytics Endpoints
# -----------------------------------------------------------------------------

@router.get(
    "/emails/dashboard/stats",
    response_model=DashboardStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve primary dashboard statistics and comparison rates",
)
async def get_dashboard_stats(
    company_id: Optional[int] = Query(None, description="Optional company ID scope"),
    email_account_id: Optional[int] = Query(None, description="Optional email account ID scope"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    all_time: bool = Query(False, description="Query complete history without lower date boundary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardStatsResponse:
    """Retrieve operational email metrics (sent, bounced, responses, bounce rate) and period comparisons."""
    return await DashboardService.get_dashboard_stats(
        db=db,
        current_user=current_user,
        company_id=company_id,
        email_account_id=email_account_id,
        date_from=date_from,
        date_to=date_to,
        all_time=all_time,
    )


@router.get(
    "/companies/{company_id}/emails/dashboard/stats",
    response_model=DashboardStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve company-scoped dashboard statistics and comparison rates",
)
async def get_company_dashboard_stats(
    company_id: int,
    email_account_id: Optional[int] = Query(None, description="Optional email account ID scope"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    all_time: bool = Query(False, description="Query complete history without lower date boundary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardStatsResponse:
    """Retrieve operational email metrics scoped to a specific company ID."""
    return await DashboardService.get_dashboard_stats(
        db=db,
        current_user=current_user,
        company_id=company_id,
        email_account_id=email_account_id,
        date_from=date_from,
        date_to=date_to,
        all_time=all_time,
    )


@router.get(
    "/emails/dashboard/activity",
    response_model=DashboardActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve daily email activity trends for the selected date range",
)
async def get_dashboard_activity(
    company_id: Optional[int] = Query(None, description="Optional company ID scope"),
    email_account_id: Optional[int] = Query(None, description="Optional email account ID scope"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    all_time: bool = Query(False, description="Query complete history without lower date boundary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardActivityResponse:
    """Retrieve daily volume points (sent, responses, bounced) for trend visualization."""
    return await DashboardService.get_activity_trends(
        db=db,
        current_user=current_user,
        company_id=company_id,
        email_account_id=email_account_id,
        date_from=date_from,
        date_to=date_to,
        all_time=all_time,
    )


@router.get(
    "/companies/{company_id}/emails/dashboard/activity",
    response_model=DashboardActivityResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve company-scoped daily email activity trends",
)
async def get_company_dashboard_activity(
    company_id: int,
    email_account_id: Optional[int] = Query(None, description="Optional email account ID scope"),
    date_from: Optional[datetime] = Query(None, description="Start date filter"),
    date_to: Optional[datetime] = Query(None, description="End date filter"),
    all_time: bool = Query(False, description="Query complete history without lower date boundary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardActivityResponse:
    """Retrieve company-scoped daily volume points (sent, responses, bounced)."""
    return await DashboardService.get_activity_trends(
        db=db,
        current_user=current_user,
        company_id=company_id,
        email_account_id=email_account_id,
        date_from=date_from,
        date_to=date_to,
        all_time=all_time,
    )


@router.get(
    "/emails/dashboard/account-health",
    response_model=AccountHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve account health and synchronization overview",
)
async def get_dashboard_account_health(
    company_id: Optional[int] = Query(None, description="Optional company ID scope"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountHealthResponse:
    """Retrieve health indicators and sync timestamps for accessible email accounts."""
    return await DashboardService.get_account_health(
        db=db,
        current_user=current_user,
        company_id=company_id,
    )


@router.get(
    "/companies/{company_id}/emails/dashboard/account-health",
    response_model=AccountHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve company-scoped account health and synchronization overview",
)
async def get_company_dashboard_account_health(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountHealthResponse:
    """Retrieve company-scoped health indicators and sync timestamps."""
    return await DashboardService.get_account_health(
        db=db,
        current_user=current_user,
        company_id=company_id,
    )
