from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.models import CompanyRole, CompanyUser
from app.modules.companies.service import CompanyService


async def get_company_membership(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyUser:
    """Authorize that the current user belongs to the requested company.
    
    Returns the CompanyUser membership object.
    Raises:
        HTTPException 404: If the company does not exist or the user is not a member.
        HTTPException 403: If the company is inactive for an existing member.
    """
    company = await CompanyService.get_company(db, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    membership = await CompanyService.get_user_membership(db, company_id, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company is inactive",
        )

    return membership


async def require_company_admin_or_owner(
    membership: CompanyUser = Depends(get_company_membership),
) -> CompanyUser:
    """Authorize that the current user has OWNER or ADMIN role in the company."""
    if membership.role not in [CompanyRole.OWNER.value, CompanyRole.ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or Administrator privileges required for this action",
        )
    return membership
