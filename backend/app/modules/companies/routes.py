from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyRole, CompanyUser
from app.modules.companies.schemas import (
    CompanyCreate,
    CompanyMemberAdd,
    CompanyMemberRead,
    CompanyWithRoleRead,
)
from app.modules.companies.service import CompanyService

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post(
    "/",
    response_model=CompanyWithRoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company organization",
)
async def create_company(
    company_in: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyWithRoleRead:
    """Create a new company. The authenticated creator is automatically assigned as OWNER."""
    company, membership = await CompanyService.create_company(
        db=db,
        name=company_in.name,
        owner_user_id=current_user.id,
    )
    return CompanyWithRoleRead(
        id=company.id,
        name=company.name,
        is_active=company.is_active,
        created_at=company.created_at,
        role=CompanyRole(membership.role),
    )


@router.get(
    "/",
    response_model=List[CompanyWithRoleRead],
    status_code=status.HTTP_200_OK,
    summary="List companies the current user belongs to",
)
async def list_my_companies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[CompanyWithRoleRead]:
    """Retrieve all active companies the authenticated user is a member of."""
    companies_with_roles = await CompanyService.get_user_companies(db, current_user.id)
    return [
        CompanyWithRoleRead(
            id=company.id,
            name=company.name,
            is_active=company.is_active,
            created_at=company.created_at,
            role=CompanyRole(role),
        )
        for company, role in companies_with_roles
    ]


@router.get(
    "/{company_id}",
    response_model=CompanyWithRoleRead,
    status_code=status.HTTP_200_OK,
    summary="Get company details by ID (membership required)",
)
async def get_company_detail(
    membership: CompanyUser = Depends(get_company_membership),
) -> CompanyWithRoleRead:
    """Retrieve company details for an authorized member."""
    company = membership.company
    return CompanyWithRoleRead(
        id=company.id,
        name=company.name,
        is_active=company.is_active,
        created_at=company.created_at,
        role=CompanyRole(membership.role),
    )


@router.get(
    "/{company_id}/members",
    response_model=List[CompanyMemberRead],
    status_code=status.HTTP_200_OK,
    summary="List all members of a company",
)
async def list_company_members(
    company_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> List[CompanyMemberRead]:
    """Retrieve all user memberships for the company."""
    members = await CompanyService.get_company_members(db, company_id)
    return [
        CompanyMemberRead(
            id=member.id,
            company_id=member.company_id,
            user_id=member.user_id,
            email=member.user.email,
            full_name=member.user.full_name,
            role=CompanyRole(member.role),
            created_at=member.created_at,
        )
        for member in members
    ]


@router.post(
    "/{company_id}/members",
    response_model=CompanyMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing user to the company (Owner/Admin only)",
)
async def add_company_member(
    company_id: int,
    member_in: CompanyMemberAdd,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CompanyMemberRead:
    """Add a registered user to the company with a specified role."""
    target_user = await AuthService.get_user_by_email(db, member_in.email)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email address was not found",
        )

    new_member = await CompanyService.add_member(
        db=db,
        company_id=company_id,
        user_id=target_user.id,
        role=member_in.role,
    )
    if not new_member:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this company",
        )

    return CompanyMemberRead(
        id=new_member.id,
        company_id=new_member.company_id,
        user_id=new_member.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=CompanyRole(new_member.role),
        created_at=new_member.created_at,
    )
