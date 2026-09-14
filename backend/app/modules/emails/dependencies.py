from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.auth.models import User
from app.modules.companies.service import CompanyService
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService


async def verify_user_can_send_from_account(
    db: AsyncSession,
    current_user: User,
    account_id: int,
    company_id: Optional[int] = None,
) -> EmailAccount:
    """Verify that the current authenticated user belongs to the company owning the email account
    and possesses authorized access to send from it.
    
    Raises:
        HTTPException 404: If account does not exist or does not match company_id.
        HTTPException 403: If user is not a company member or lacks granted access.
    """
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found.",
        )

    if company_id is not None and account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account does not belong to the specified company.",
        )

    membership = await CompanyService.get_user_membership(
        db=db,
        company_id=account.company_id,
        user_id=current_user.id,
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to the company that owns this email account.",
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
            detail="You do not have permission to send emails from this email account.",
        )

    return account


# Reusable alias for general account access (sending, syncing, viewing)
verify_user_can_access_account = verify_user_can_send_from_account

