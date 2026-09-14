from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.dependencies import get_company_membership
from app.modules.companies.models import CompanyUser
from app.modules.email_accounts.models import EmailAccount
from app.modules.email_accounts.service import EmailAccountService


async def get_authorized_email_account(
    company_id: int,
    account_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmailAccount:
    """Validate that the requested email account belongs to the company and the user is authorized to access it."""
    account = await EmailAccountService.get_email_account(db, account_id)
    if not account or account.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found in this company",
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
            detail="You do not have permission to access this email account",
        )

    return account
