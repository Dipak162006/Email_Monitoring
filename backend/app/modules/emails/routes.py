from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.models import CompanyRole
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.dependencies import (
    verify_user_can_access_account,
    verify_user_can_access_email,
    verify_user_can_send_from_account,
)
from app.modules.emails.draft_service import EmailDraftService
from app.modules.emails.mailbox_service import EmailMailboxService
from app.modules.emails.schemas import (
    EmailDraftCreate,
    EmailDraftUpdate,
    EmailListResponse,
    EmailRead,
    EmailReadUpdate,
    EmailSendRequest,
    EmailStarUpdate,
    EmailSyncRequest,
    EmailSyncResult,
    EmailThreadDetail,
    EmailThreadRead,
    ThreadListResponse,
)
from app.modules.emails.service import EmailService
from app.modules.emails.sync_service import EmailSyncService
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
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
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

        emails, total = await EmailMailboxService.list_emails(
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
            emails, total = await EmailMailboxService.list_emails(
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

            emails, total = await EmailMailboxService.list_emails(
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
        emails=[EmailRead.model_validate(e) for e in emails],
        total=total,
        limit=limit,
        offset=offset,
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
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
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
    response_model=EmailSyncResult,
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand IMAP synchronization for an authorized email account",
)
async def sync_email_account(
    account_id: int,
    sync_req: Optional[EmailSyncRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSyncResult:
    """Synchronize incoming messages from IMAP server into local database."""
    account = await verify_user_can_access_account(
        db=db,
        current_user=current_user,
        account_id=account_id,
    )
    req = sync_req or EmailSyncRequest()
    sync_service = EmailSyncService()
    return await sync_service.sync_mailbox(
        db=db,
        account=account,
        folder=req.folder,
        max_messages=req.max_messages,
    )


@router.post(
    "/companies/{company_id}/email-accounts/{account_id}/sync",
    response_model=EmailSyncResult,
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand IMAP synchronization scoped to a company",
)
async def sync_company_email_account(
    company_id: int,
    account_id: int,
    sync_req: Optional[EmailSyncRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailSyncResult:
    """Synchronize incoming messages scoped to a specific company ID."""
    account = await verify_user_can_access_account(
        db=db,
        current_user=current_user,
        account_id=account_id,
        company_id=company_id,
    )
    req = sync_req or EmailSyncRequest()
    sync_service = EmailSyncService()
    return await sync_service.sync_mailbox(
        db=db,
        account=account,
        folder=req.folder,
        max_messages=req.max_messages,
    )


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


