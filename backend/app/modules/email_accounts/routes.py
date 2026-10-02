from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyUser
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.dependencies import get_authorized_email_account
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.schemas import (
    EmailAccountAccessGrant,
    EmailAccountAccessRead,
    EmailAccountCreate,
    EmailAccountRead,
    EmailAccountUpdate,
)
from app.modules.email_accounts.service import EmailAccountService

router = APIRouter(tags=["Email Accounts"])


# -----------------------------------------------------------------------------
# Company-scoped Email Account Management
# -----------------------------------------------------------------------------

@router.post(
    "/companies/{company_id}/email-accounts",
    response_model=EmailAccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new email account for a company (Admin/Owner only)",
)
async def create_email_account(
    company_id: int,
    account_in: EmailAccountCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> EmailAccountRead:
    """Create a company email account with encrypted SMTP/IMAP credentials."""
    account = await EmailAccountService.create_email_account(
        db=db,
        company_id=company_id,
        account_in=account_in,
    )
    return EmailAccountService.to_read_schema(account)


@router.get(
    "/companies/{company_id}/email-accounts",
    response_model=List[EmailAccountRead],
    status_code=status.HTTP_200_OK,
    summary="List email accounts in a company accessible to current user",
)
async def list_company_email_accounts(
    company_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EmailAccountRead]:
    """List email accounts. Owners/Admins see all accounts; Members see only granted accounts."""
    accounts = await EmailAccountService.get_user_accessible_accounts_for_company(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        user_role=membership.role,
    )
    return [EmailAccountService.to_read_schema(acc) for acc in accounts]


@router.get(
    "/companies/{company_id}/email-accounts/{account_id}",
    response_model=EmailAccountRead,
    status_code=status.HTTP_200_OK,
    summary="Get email account details by ID (authorized access required)",
)
async def get_email_account(
    account: EmailAccount = Depends(get_authorized_email_account),
) -> EmailAccountRead:
    """Retrieve email account details. Passwords are never returned."""
    return EmailAccountService.to_read_schema(account)


@router.put(
    "/companies/{company_id}/email-accounts/{account_id}",
    response_model=EmailAccountRead,
    status_code=status.HTTP_200_OK,
    summary="Update an email account (Admin/Owner only)",
)
async def update_email_account(
    company_id: int,
    account_id: int,
    account_in: EmailAccountUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> EmailAccountRead:
    """Update email account configuration and optionally rotate credentials."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
        )

    updated = await EmailAccountService.update_email_account(
        db=db,
        account=account,
        account_in=account_in,
    )
    return EmailAccountService.to_read_schema(updated)


@router.delete(
    "/companies/{company_id}/email-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an email account (Admin/Owner only)",
)
async def delete_email_account(
    company_id: int,
    account_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Delete a company email account and cascade-remove all access permissions."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
        )

    from app.modules.emails.attachment_service import AttachmentService
    # Collect candidate storage paths prior to account deletion
    candidate_paths = await AttachmentService.get_account_attachment_paths(db, account_id)

    await db.delete(account)
    await db.commit()

    # Clean up physical files on disk only after database deletion succeeds
    await AttachmentService.cleanup_unreferenced_storage_paths(db, candidate_paths)
    return None


# -----------------------------------------------------------------------------
# User Access Grants for Email Accounts
# -----------------------------------------------------------------------------

@router.get(
    "/companies/{company_id}/email-accounts-access",
    response_model=List[EmailAccountAccessRead],
    status_code=status.HTTP_200_OK,
    summary="List all email account access permissions for a company (Admin/Owner only)",
)
async def list_company_email_accounts_access(
    company_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> List[EmailAccountAccessRead]:
    """List all explicit user access permissions across all email accounts in this company."""
    return await EmailAccountService.get_company_access_list(db, company_id)


@router.get(
    "/companies/{company_id}/email-accounts/{account_id}/access",
    response_model=List[EmailAccountAccessRead],
    status_code=status.HTTP_200_OK,
    summary="List users who have explicit access to an email account (Admin/Owner only)",
)
async def list_email_account_access(
    company_id: int,
    account_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> List[EmailAccountAccessRead]:
    """List all explicit user access permissions for this email account."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
        )

    return await EmailAccountService.get_access_list(db, account_id)


@router.post(
    "/companies/{company_id}/email-accounts/{account_id}/access",
    response_model=EmailAccountAccessRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a company member access to an email account (Admin/Owner only)",
)
async def grant_email_account_access(
    company_id: int,
    account_id: int,
    grant_in: EmailAccountAccessGrant,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> EmailAccountAccessRead:
    """Grant email account access. Target user must be a member of this company."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
        )

    # Validate that target user belongs to this company
    target_membership = await CompanyService.get_user_membership(db, company_id, grant_in.user_id)
    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant access: User is not a member of this company",
        )

    target_user = await AuthService.get_user_by_id(db, grant_in.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user does not exist",
        )

    access = await EmailAccountService.grant_access(db, account_id, grant_in.user_id)
    if not access:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has access to this email account",
        )

    return EmailAccountAccessRead(
        id=access.id,
        email_account_id=access.email_account_id,
        user_id=access.user_id,
        user_email=target_user.email,
        user_full_name=target_user.full_name,
        created_at=access.created_at,
    )


@router.delete(
    "/companies/{company_id}/email-accounts/{account_id}/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a user's access to an email account (Admin/Owner only)",
)
async def revoke_email_account_access(
    company_id: int,
    account_id: int,
    user_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a user's access to an email account."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
        )

    revoked = await EmailAccountService.revoke_access(db, account_id, user_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have explicit access to this email account",
        )
    return None


# -----------------------------------------------------------------------------
# Cross-Company Authorized Accounts (for Compose From field)
# -----------------------------------------------------------------------------

@router.get(
    "/email-accounts/authorized",
    response_model=List[EmailAccountRead],
    status_code=status.HTTP_200_OK,
    summary="List all email accounts current user is authorized to use across all companies",
)
async def list_all_authorized_email_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EmailAccountRead]:
    """Retrieve all company email accounts the user is authorized to send/receive from."""
    accounts = await EmailAccountService.get_all_user_authorized_accounts(db, current_user.id)
    return [EmailAccountService.to_read_schema(acc) for acc in accounts]
