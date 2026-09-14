from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.companies.models import Company, CompanyRole, CompanyUser


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
