from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.emails.dependencies import verify_user_can_access_account, verify_user_can_send_from_account
from app.modules.emails.schemas import EmailRead, EmailSendRequest, EmailSyncRequest, EmailSyncResult
from app.modules.emails.service import EmailService
from app.modules.emails.sync_service import EmailSyncService

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

