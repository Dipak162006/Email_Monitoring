from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.models import CompanyRole
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.service import EmailAccountService
from app.modules.emails.dependencies import verify_user_can_access_account, verify_user_can_send_from_account
from app.modules.emails.schemas import (
    EmailRead,
    EmailSendRequest,
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


@router.get(
    "/emails/{email_id}",
    response_model=EmailRead,
    status_code=status.HTTP_200_OK,
    summary="Get email details by ID (must belong to user's company)",
)
async def get_email_by_id(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailRead:
    """Retrieve details and delivery status of an email record."""
    email_record = await EmailService.get_email(db, email_id)
    if not email_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found.",
        )

    # Check that user is a member of the company that owns this email
    membership = await CompanyService.get_user_membership(
        db=db,
        company_id=email_record.company_id,
        user_id=current_user.id,
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to view this email.",
        )

    return EmailRead.model_validate(email_record)


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


