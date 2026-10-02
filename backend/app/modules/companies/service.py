from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.auth.service import AuthService
from app.modules.companies.models import (
    Company,
    CompanyInvitation,
    CompanyRole,
    CompanyUser,
    InvitationStatus,
)


class CompanyService:
    """Service handling company tenant operations and membership data access."""

    @staticmethod
    async def create_company(
        db: AsyncSession,
        name: str,
        owner_user_id: int,
    ) -> Tuple[Company, CompanyUser]:
        """Create a new company organization and automatically assign the creator as OWNER."""
        company = Company(name=name.strip(), is_active=True)
        db.add(company)
        await db.flush()  # populate company.id

        membership = CompanyUser(
            company_id=company.id,
            user_id=owner_user_id,
            role=CompanyRole.OWNER.value,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(company)
        await db.refresh(membership)
        return company, membership

    @staticmethod
    async def get_company(db: AsyncSession, company_id: int) -> Optional[Company]:
        """Fetch a company by ID."""
        result = await db.execute(select(Company).where(Company.id == company_id))
        return result.scalars().first()

    @staticmethod
    async def update_company(
        db: AsyncSession,
        company: Company,
        name: str,
    ) -> Company:
        """Update company name and persist using standard transaction conventions."""
        company.name = name.strip()
        await db.commit()
        await db.refresh(company)
        return company

    @staticmethod
    async def get_user_membership(
        db: AsyncSession,
        company_id: int,
        user_id: int,
    ) -> Optional[CompanyUser]:
        """Fetch a specific user's membership in a company with company preloaded."""
        query = (
            select(CompanyUser)
            .options(selectinload(CompanyUser.company))
            .where(
                CompanyUser.company_id == company_id,
                CompanyUser.user_id == user_id,
            )
        )
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def get_user_companies(
        db: AsyncSession,
        user_id: int,
    ) -> List[Tuple[Company, str]]:
        """Fetch all active companies the user belongs to along with their role."""
        query = (
            select(Company, CompanyUser.role)
            .join(CompanyUser, Company.id == CompanyUser.company_id)
            .where(CompanyUser.user_id == user_id, Company.is_active == True)  # noqa: E712
            .order_by(Company.name.asc())
        )
        result = await db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def get_company_members(
        db: AsyncSession,
        company_id: int,
    ) -> List[CompanyUser]:
        """Fetch all user memberships for a company with user details preloaded."""
        query = (
            select(CompanyUser)
            .options(selectinload(CompanyUser.user))
            .where(CompanyUser.company_id == company_id)
            .order_by(CompanyUser.created_at.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def add_member(
        db: AsyncSession,
        company_id: int,
        user_id: int,
        role: CompanyRole = CompanyRole.MEMBER,
    ) -> Optional[CompanyUser]:
        """Add an existing user as a member of a company."""
        existing = await CompanyService.get_user_membership(db, company_id, user_id)
        if existing:
            return None

        membership = CompanyUser(
            company_id=company_id,
            user_id=user_id,
            role=role.value,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(membership)
        return membership

    @staticmethod
    async def update_member_role(
        db: AsyncSession,
        company_id: int,
        operator_role: str,
        target_user_id: int,
        new_role: CompanyRole,
        operator_user_id: Optional[int] = None,
    ) -> CompanyUser:
        """Update a member's role within a company, enforcing ownership and self-modification protection."""
        if operator_user_id is not None and operator_user_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role.",
            )

        query = (
            select(CompanyUser)
            .options(selectinload(CompanyUser.user))
            .where(
                CompanyUser.company_id == company_id,
                CompanyUser.user_id == target_user_id,
            )
        )
        result = await db.execute(query)
        target_membership = result.scalars().first()

        if not target_membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this company",
            )

        if target_membership.role == CompanyRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify the role of the workspace Owner",
            )

        if new_role not in [CompanyRole.ADMIN, CompanyRole.MEMBER]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role selection. Only ADMIN or MEMBER can be assigned.",
            )

        target_membership.role = new_role.value
        await db.commit()
        await db.refresh(target_membership)
        return target_membership

    @staticmethod
    async def remove_member(
        db: AsyncSession,
        company_id: int,
        operator_role: str,
        target_user_id: int,
        operator_user_id: Optional[int] = None,
    ) -> bool:
        """Remove a member from a company and revoke company-specific email account access.
        
        The User account itself is NOT deleted, preserving user identity across other companies.
        The workspace OWNER cannot be removed, and users cannot remove themselves.
        """
        if operator_user_id is not None and operator_user_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot remove yourself from the company.",
            )

        query = (
            select(CompanyUser)
            .where(
                CompanyUser.company_id == company_id,
                CompanyUser.user_id == target_user_id,
            )
        )
        result = await db.execute(query)
        target_membership = result.scalars().first()

        if not target_membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this company",
            )

        if target_membership.role == CompanyRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN if operator_role == CompanyRole.ADMIN.value else status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the workspace Owner. Transfer ownership first.",
            )

        # Remove explicit email account access permissions for this company's accounts
        from app.modules.email_accounts.models import EmailAccount, EmailAccountAccess

        delete_access_stmt = (
            delete(EmailAccountAccess)
            .where(
                EmailAccountAccess.user_id == target_user_id,
                EmailAccountAccess.email_account_id.in_(
                    select(EmailAccount.id).where(EmailAccount.company_id == company_id)
                ),
            )
        )
        await db.execute(delete_access_stmt)

        # Remove the company membership
        await db.delete(target_membership)
        await db.commit()
        return True

    @staticmethod
    async def create_invitation(
        db: AsyncSession,
        company_id: int,
        inviter_user_id: int,
        email: str,
        role: CompanyRole = CompanyRole.MEMBER,
    ) -> CompanyInvitation:
        """Create a company invitation for a user with proposed role."""
        normalized_email = email.lower().strip()
        if role not in [CompanyRole.ADMIN, CompanyRole.MEMBER]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only Admin or Member roles can be assigned in invitations.",
            )

        # Check if user with this email is already a member
        user = await AuthService.get_user_by_email(db, normalized_email)
        if user:
            existing_membership = await CompanyService.get_user_membership(db, company_id, user.id)
            if existing_membership:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already a member of this company",
                )

        # Check if there is an active pending invitation
        existing_inv = (
            await db.execute(
                select(CompanyInvitation).where(
                    CompanyInvitation.company_id == company_id,
                    func.lower(CompanyInvitation.invited_email) == normalized_email,
                    CompanyInvitation.status == InvitationStatus.PENDING.value,
                )
            )
        ).scalars().first()
        if existing_inv:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending invitation already exists for this email address",
            )

        invitation = CompanyInvitation(
            company_id=company_id,
            invited_email=normalized_email,
            invited_user_id=user.id if user else None,
            inviter_user_id=inviter_user_id,
            role=role.value,
            status=InvitationStatus.PENDING.value,
        )
        db.add(invitation)
        await db.commit()
        return await CompanyService.get_invitation_by_id(db, invitation.id)

    @staticmethod
    async def get_invitation_by_id(
        db: AsyncSession,
        invitation_id: int,
    ) -> Optional[CompanyInvitation]:
        """Fetch an invitation by ID with relationships preloaded."""
        query = (
            select(CompanyInvitation)
            .options(
                selectinload(CompanyInvitation.inviter),
                selectinload(CompanyInvitation.invited_user),
                selectinload(CompanyInvitation.company),
            )
            .where(CompanyInvitation.id == invitation_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def get_company_invitations(
        db: AsyncSession,
        company_id: int,
        status_filter: Optional[InvitationStatus] = None,
    ) -> List[CompanyInvitation]:
        """Fetch all invitations created for a company."""
        query = (
            select(CompanyInvitation)
            .options(
                selectinload(CompanyInvitation.inviter),
                selectinload(CompanyInvitation.invited_user),
                selectinload(CompanyInvitation.company),
            )
            .where(CompanyInvitation.company_id == company_id)
            .order_by(CompanyInvitation.created_at.desc())
        )
        if status_filter:
            query = query.where(CompanyInvitation.status == status_filter.value)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_pending_invitations(
        db: AsyncSession,
        user_email: str,
    ) -> List[CompanyInvitation]:
        """Fetch all pending invitations for a specific user email."""
        normalized_email = user_email.lower().strip()
        query = (
            select(CompanyInvitation)
            .options(
                selectinload(CompanyInvitation.inviter),
                selectinload(CompanyInvitation.company),
            )
            .where(
                func.lower(CompanyInvitation.invited_email) == normalized_email,
                CompanyInvitation.status == InvitationStatus.PENDING.value,
            )
            .order_by(CompanyInvitation.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def accept_invitation(
        db: AsyncSession,
        invitation_id: int,
        user_id: int,
        user_email: str,
    ) -> Tuple[Company, CompanyUser]:
        """Accept an invitation to join a company workspace."""
        invitation = await CompanyService.get_invitation_by_id(db, invitation_id)
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.invited_email.lower().strip() != user_email.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to accept this invitation",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation cannot be accepted because it has already been {invitation.status.lower()}",
            )

        # Check if already a member
        membership = await CompanyService.get_user_membership(db, invitation.company_id, user_id)
        if not membership:
            membership = CompanyUser(
                company_id=invitation.company_id,
                user_id=user_id,
                role=invitation.role,
            )
            db.add(membership)
        else:
            membership.role = invitation.role

        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = func.now()
        invitation.invited_user_id = user_id

        await db.commit()
        await db.refresh(membership)
        company = await CompanyService.get_company(db, invitation.company_id)
        return company, membership

    @staticmethod
    async def decline_invitation(
        db: AsyncSession,
        invitation_id: int,
        user_id: int,
        user_email: str,
    ) -> CompanyInvitation:
        """Decline a company invitation."""
        invitation = await CompanyService.get_invitation_by_id(db, invitation_id)
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.invited_email.lower().strip() != user_email.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to decline this invitation",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation cannot be declined because it has already been {invitation.status.lower()}",
            )

        invitation.status = InvitationStatus.DECLINED.value
        invitation.declined_at = func.now()
        invitation.invited_user_id = user_id

        await db.commit()
        await db.refresh(invitation)
        return invitation

    @staticmethod
    async def revoke_invitation(
        db: AsyncSession,
        company_id: int,
        invitation_id: int,
    ) -> CompanyInvitation:
        """Revoke a pending company invitation (Owner/Admin only)."""
        invitation = await CompanyService.get_invitation_by_id(db, invitation_id)
        if not invitation or invitation.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation cannot be revoked because it is already {invitation.status.lower()}",
            )

        invitation.status = InvitationStatus.REVOKED.value
        invitation.updated_at = func.now()

        await db.commit()
        await db.refresh(invitation)
        return invitation

    @staticmethod
    async def resend_invitation(
        db: AsyncSession,
        company_id: int,
        invitation_id: int,
    ) -> CompanyInvitation:
        """Resend (refresh) a pending company invitation (Owner/Admin only)."""
        invitation = await CompanyService.get_invitation_by_id(db, invitation_id)
        if not invitation or invitation.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation cannot be resent because it is already {invitation.status.lower()}",
            )

        invitation.updated_at = func.now()

        await db.commit()
        await db.refresh(invitation)
        return invitation


