from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyRole, CompanyUser, InvitationStatus
from app.modules.companies.schemas import (
    CompanyCreate,
    CompanyInvitationCreate,
    CompanyInvitationRead,
    CompanyMemberAdd,
    CompanyMemberRead,
    CompanyMemberRoleUpdate,
    CompanyUpdate,
    CompanyWithRoleRead,
    UserInvitationRead,
)
from app.modules.companies.service import CompanyService

router = APIRouter(prefix="/companies", tags=["Companies"])
invitations_router = APIRouter(prefix="/invitations", tags=["Invitations"])


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


@router.patch(
    "/{company_id}",
    response_model=CompanyWithRoleRead,
    status_code=status.HTTP_200_OK,
    summary="Update company settings (Owner/Admin only)",
)
async def update_company(
    company_id: int,
    company_update: CompanyUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CompanyWithRoleRead:
    """Update company settings (name). Accessible only by workspace OWNER or ADMIN."""
    company = membership.company
    updated_company = await CompanyService.update_company(
        db=db,
        company=company,
        name=company_update.name,
    )
    return CompanyWithRoleRead(
        id=updated_company.id,
        name=updated_company.name,
        is_active=updated_company.is_active,
        created_at=updated_company.created_at,
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
            is_active=member.user.is_active,
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
        is_active=target_user.is_active,
        created_at=new_member.created_at,
    )


@router.put(
    "/{company_id}/members/{user_id}/role",
    response_model=CompanyMemberRead,
    status_code=status.HTTP_200_OK,
    summary="Change a company member's role (Admin/Owner only)",
)
async def update_company_member_role(
    company_id: int,
    user_id: int,
    role_in: CompanyMemberRoleUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CompanyMemberRead:
    """Update a company member's role (Admin or Member). Owner is protected."""
    updated = await CompanyService.update_member_role(
        db=db,
        company_id=company_id,
        operator_role=membership.role,
        target_user_id=user_id,
        new_role=role_in.role,
        operator_user_id=membership.user_id,
    )
    return CompanyMemberRead(
        id=updated.id,
        company_id=updated.company_id,
        user_id=updated.user_id,
        email=updated.user.email,
        full_name=updated.user.full_name,
        role=CompanyRole(updated.role),
        is_active=updated.user.is_active,
        created_at=updated.created_at,
    )


@router.delete(
    "/{company_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from the company (Admin/Owner only)",
)
async def remove_company_member(
    company_id: int,
    user_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the company and revoke their company email account access."""
    await CompanyService.remove_member(
        db=db,
        company_id=company_id,
        operator_role=membership.role,
        target_user_id=user_id,
        operator_user_id=membership.user_id,
    )
    return None


# ---------------------------------------------------------
# Company-scoped invitation management (Owner/Admin)
# ---------------------------------------------------------

@router.post(
    "/{company_id}/invitations",
    response_model=CompanyInvitationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create/send an invitation to join the company (Owner/Admin only)",
)
async def create_company_invitation(
    company_id: int,
    invitation_in: CompanyInvitationCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CompanyInvitationRead:
    """Create a company invitation for the specified email and role."""
    invitation = await CompanyService.create_invitation(
        db=db,
        company_id=company_id,
        inviter_user_id=membership.user_id,
        email=invitation_in.email,
        role=invitation_in.role,
    )
    return CompanyInvitationRead(
        id=invitation.id,
        company_id=invitation.company_id,
        company_name=invitation.company.name if invitation.company else None,
        invited_email=invitation.invited_email,
        invited_user_id=invitation.invited_user_id,
        inviter_user_id=invitation.inviter_user_id,
        inviter_email=invitation.inviter.email if invitation.inviter else None,
        inviter_name=invitation.inviter.full_name if invitation.inviter else None,
        role=CompanyRole(invitation.role),
        status=InvitationStatus(invitation.status),
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        accepted_at=invitation.accepted_at,
        declined_at=invitation.declined_at,
    )


@router.get(
    "/{company_id}/invitations",
    response_model=List[CompanyInvitationRead],
    status_code=status.HTTP_200_OK,
    summary="List all invitations for the company (Owner/Admin only)",
)
async def list_company_invitations(
    company_id: int,
    status_filter: Optional[InvitationStatus] = Query(None, description="Filter by status (PENDING, ACCEPTED, DECLINED, REVOKED)"),
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> List[CompanyInvitationRead]:
    """Retrieve all invitations issued for this company."""
    invitations = await CompanyService.get_company_invitations(
        db=db,
        company_id=company_id,
        status_filter=status_filter,
    )
    return [
        CompanyInvitationRead(
            id=inv.id,
            company_id=inv.company_id,
            company_name=inv.company.name if inv.company else None,
            invited_email=inv.invited_email,
            invited_user_id=inv.invited_user_id,
            inviter_user_id=inv.inviter_user_id,
            inviter_email=inv.inviter.email if inv.inviter else None,
            inviter_name=inv.inviter.full_name if inv.inviter else None,
            role=CompanyRole(inv.role),
            status=InvitationStatus(inv.status),
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            accepted_at=inv.accepted_at,
            declined_at=inv.declined_at,
        )
        for inv in invitations
    ]


@router.delete(
    "/{company_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a pending company invitation (Owner/Admin only)",
)
async def revoke_company_invitation(
    company_id: int,
    invitation_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an outstanding invitation. Foreign-company or nonexistent invitations return 404."""
    await CompanyService.revoke_invitation(
        db=db,
        company_id=company_id,
        invitation_id=invitation_id,
    )
    return None


@router.post(
    "/{company_id}/invitations/{invitation_id}/resend",
    response_model=CompanyInvitationRead,
    status_code=status.HTTP_200_OK,
    summary="Resend a pending company invitation (Owner/Admin only)",
)
async def resend_company_invitation(
    company_id: int,
    invitation_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CompanyInvitationRead:
    """Refresh a pending invitation timestamp without modifying created_at."""
    invitation = await CompanyService.resend_invitation(
        db=db,
        company_id=company_id,
        invitation_id=invitation_id,
    )
    return CompanyInvitationRead(
        id=invitation.id,
        company_id=invitation.company_id,
        company_name=invitation.company.name if invitation.company else None,
        invited_email=invitation.invited_email,
        invited_user_id=invitation.invited_user_id,
        inviter_user_id=invitation.inviter_user_id,
        inviter_email=invitation.inviter.email if invitation.inviter else None,
        inviter_name=invitation.inviter.full_name if invitation.inviter else None,
        role=CompanyRole(invitation.role),
        status=InvitationStatus(invitation.status),
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
        accepted_at=invitation.accepted_at,
        declined_at=invitation.declined_at,
    )


# ---------------------------------------------------------
# User-scoped pending invitation endpoints
# ---------------------------------------------------------

@invitations_router.get(
    "/my-pending",
    response_model=List[UserInvitationRead],
    status_code=status.HTTP_200_OK,
    summary="List pending workspace invitations for the current user",
)
async def list_my_pending_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[UserInvitationRead]:
    """Retrieve all pending company invitations addressed to the authenticated user's email."""
    invitations = await CompanyService.get_user_pending_invitations(
        db=db,
        user_email=current_user.email,
    )
    return [
        UserInvitationRead(
            id=inv.id,
            company_id=inv.company_id,
            company_name=inv.company.name if inv.company else "Unknown Company",
            role=CompanyRole(inv.role),
            inviter_email=inv.inviter.email if inv.inviter else "Unknown",
            inviter_name=inv.inviter.full_name if inv.inviter else None,
            status=InvitationStatus(inv.status),
            created_at=inv.created_at,
        )
        for inv in invitations
    ]


@invitations_router.post(
    "/{invitation_id}/accept",
    response_model=CompanyWithRoleRead,
    status_code=status.HTTP_200_OK,
    summary="Accept a pending workspace invitation",
)
async def accept_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompanyWithRoleRead:
    """Accept an invitation to join a company workspace."""
    company, membership = await CompanyService.accept_invitation(
        db=db,
        invitation_id=invitation_id,
        user_id=current_user.id,
        user_email=current_user.email,
    )
    return CompanyWithRoleRead(
        id=company.id,
        name=company.name,
        is_active=company.is_active,
        created_at=company.created_at,
        role=CompanyRole(membership.role),
    )


@invitations_router.post(
    "/{invitation_id}/decline",
    response_model=UserInvitationRead,
    status_code=status.HTTP_200_OK,
    summary="Decline a pending workspace invitation",
)
async def decline_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserInvitationRead:
    """Decline an invitation to join a company workspace."""
    invitation = await CompanyService.decline_invitation(
        db=db,
        invitation_id=invitation_id,
        user_id=current_user.id,
        user_email=current_user.email,
    )
    return UserInvitationRead(
        id=invitation.id,
        company_id=invitation.company_id,
        company_name=invitation.company.name if invitation.company else "Unknown Company",
        role=CompanyRole(invitation.role),
        inviter_email=invitation.inviter.email if invitation.inviter else "Unknown",
        inviter_name=invitation.inviter.full_name if invitation.inviter else None,
        status=InvitationStatus(invitation.status),
        created_at=invitation.created_at,
    )

