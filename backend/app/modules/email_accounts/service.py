from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.security import encrypt_credential
from app.modules.companies.models import CompanyRole
from app.modules.domains.models import Domain
from app.modules.domains.schemas import normalize_domain_name
from app.modules.email_accounts.models import EmailAccount, EmailAccountAccess, EmailProvider, SecurityMode
from app.modules.email_accounts.schemas import (
    EmailAccountAccessRead,
    EmailAccountCreate,
    EmailAccountRead,
    EmailAccountUpdate,
)


class EmailAccountService:
    """Service layer handling company email account CRUD, encryption, and user access permissions."""

    @staticmethod
    def to_read_schema(account: EmailAccount) -> EmailAccountRead:
        """Serialize an EmailAccount model safely without exposing encrypted or plaintext secrets."""
        return EmailAccountRead(
            id=account.id,
            company_id=account.company_id,
            name=account.name,
            email_address=account.email_address,
            provider=EmailProvider(account.provider),
            domain_id=account.domain_id,
            smtp_host=account.smtp_host,
            smtp_port=account.smtp_port,
            smtp_security=SecurityMode(account.smtp_security) if account.smtp_security else None,
            smtp_username=account.smtp_username,
            has_smtp_password=bool(account.smtp_password_encrypted),
            imap_host=account.imap_host,
            imap_port=account.imap_port,
            imap_security=SecurityMode(account.imap_security) if account.imap_security else None,
            imap_username=account.imap_username,
            has_imap_password=bool(account.imap_password_encrypted),
            is_active=account.is_active,
            last_synced_at=account.last_synced_at,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    @staticmethod
    async def validate_email_account_domain_assignment(
        db: AsyncSession,
        company_id: int,
        email_address: str,
        domain_id: Optional[int],
    ) -> Optional[Domain]:
        """Validate that domain exists, belongs to same company, and matches the email address domain.
        
        Returns the Domain instance if valid, or None if domain_id is None.
        Raises:
            HTTPException(404): If domain does not exist or belongs to another company (company isolation).
            HTTPException(422): If email address domain part does not match assigned domain name.
        """
        if domain_id is None:
            return None

        result = await db.execute(
            select(Domain).where(
                Domain.id == domain_id,
                Domain.company_id == company_id,
            )
        )
        domain = result.scalar_one_or_none()
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found in this company",
            )

        email_str = str(email_address).lower().strip()
        if "@" in email_str:
            email_domain_raw = email_str.split("@", 1)[1]
            try:
                email_domain_normalized = normalize_domain_name(email_domain_raw)
            except Exception:
                email_domain_normalized = email_domain_raw

            if email_domain_normalized != domain.domain_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Email address domain '{email_domain_normalized}' does not match assigned domain '{domain.domain_name}'",
                )

        return domain

    @staticmethod
    async def create_email_account(
        db: AsyncSession,
        company_id: int,
        account_in: EmailAccountCreate,
    ) -> EmailAccount:
        """Create a new company email account with encrypted credentials at rest."""
        if account_in.domain_id is not None:
            await EmailAccountService.validate_email_account_domain_assignment(
                db=db,
                company_id=company_id,
                email_address=account_in.email_address,
                domain_id=account_in.domain_id,
            )

        smtp_pw_encrypted = encrypt_credential(account_in.smtp_password)
        imap_pw_encrypted = encrypt_credential(account_in.imap_password)

        account = EmailAccount(
            company_id=company_id,
            name=account_in.name.strip(),
            email_address=str(account_in.email_address).lower().strip(),
            provider=account_in.provider.value,
            domain_id=account_in.domain_id,
            smtp_host=account_in.smtp_host,
            smtp_port=account_in.smtp_port,
            smtp_security=account_in.smtp_security.value if account_in.smtp_security else None,
            smtp_username=account_in.smtp_username,
            smtp_password_encrypted=smtp_pw_encrypted,
            imap_host=account_in.imap_host,
            imap_port=account_in.imap_port,
            imap_security=account_in.imap_security.value if account_in.imap_security else None,
            imap_username=account_in.imap_username,
            imap_password_encrypted=imap_pw_encrypted,
            is_active=True,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account

    @staticmethod
    async def update_email_account(
        db: AsyncSession,
        account: EmailAccount,
        account_in: EmailAccountUpdate,
    ) -> EmailAccount:
        """Update email account fields and optionally rotate encrypted credentials."""
        target_email = (
            str(account_in.email_address).lower().strip()
            if account_in.email_address is not None
            else account.email_address
        )

        if "domain_id" in account_in.model_fields_set:
            if account_in.domain_id is not None:
                await EmailAccountService.validate_email_account_domain_assignment(
                    db=db,
                    company_id=account.company_id,
                    email_address=target_email,
                    domain_id=account_in.domain_id,
                )
            account.domain_id = account_in.domain_id
        elif account_in.email_address is not None and account.domain_id is not None:
            # Email address changed while assigned to an existing domain: validate compatibility
            await EmailAccountService.validate_email_account_domain_assignment(
                db=db,
                company_id=account.company_id,
                email_address=target_email,
                domain_id=account.domain_id,
            )

        if account_in.name is not None:
            account.name = account_in.name.strip()
        if account_in.email_address is not None:
            account.email_address = target_email
        if account_in.provider is not None:
            account.provider = account_in.provider.value
        if account_in.smtp_host is not None:
            account.smtp_host = account_in.smtp_host
        if account_in.smtp_port is not None:
            account.smtp_port = account_in.smtp_port
        if account_in.smtp_security is not None:
            account.smtp_security = account_in.smtp_security.value
        if account_in.smtp_username is not None:
            account.smtp_username = account_in.smtp_username
        if account_in.smtp_password is not None:
            account.smtp_password_encrypted = encrypt_credential(account_in.smtp_password)

        if account_in.imap_host is not None:
            account.imap_host = account_in.imap_host
        if account_in.imap_port is not None:
            account.imap_port = account_in.imap_port
        if account_in.imap_security is not None:
            account.imap_security = account_in.imap_security.value
        if account_in.imap_username is not None:
            account.imap_username = account_in.imap_username
        if account_in.imap_password is not None:
            account.imap_password_encrypted = encrypt_credential(account_in.imap_password)

        if account_in.is_active is not None:
            account.is_active = account_in.is_active

        await db.commit()
        await db.refresh(account)
        return account

    @staticmethod
    async def get_email_account(db: AsyncSession, account_id: int) -> Optional[EmailAccount]:
        """Fetch an email account by its database ID."""
        result = await db.execute(select(EmailAccount).where(EmailAccount.id == account_id))
        return result.scalars().first()

    @staticmethod
    async def get_company_email_accounts(db: AsyncSession, company_id: int) -> List[EmailAccount]:
        """Fetch all email accounts belonging to a company."""
        query = (
            select(EmailAccount)
            .where(EmailAccount.company_id == company_id)
            .order_by(EmailAccount.name.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def check_user_access(
        db: AsyncSession,
        account: EmailAccount,
        user_id: int,
        user_role: str,
    ) -> bool:
        """Check if user has permission to access the email account.
        
        Company OWNER and ADMIN roles have full access to all company email accounts.
        MEMBER role requires an explicit record in email_account_access.
        """
        if user_role in [CompanyRole.OWNER.value, CompanyRole.ADMIN.value]:
            return True

        query = select(EmailAccountAccess).where(
            EmailAccountAccess.email_account_id == account.id,
            EmailAccountAccess.user_id == user_id,
        )
        result = await db.execute(query)
        return result.scalars().first() is not None

    @staticmethod
    async def get_user_accessible_accounts_for_company(
        db: AsyncSession,
        company_id: int,
        user_id: int,
        user_role: str,
    ) -> List[EmailAccount]:
        """Fetch email accounts the user is authorized to see within a specific company."""
        if user_role in [CompanyRole.OWNER.value, CompanyRole.ADMIN.value]:
            return await EmailAccountService.get_company_email_accounts(db, company_id)

        # For regular members, join with email_account_access
        query = (
            select(EmailAccount)
            .join(EmailAccountAccess, EmailAccount.id == EmailAccountAccess.email_account_id)
            .where(
                EmailAccount.company_id == company_id,
                EmailAccountAccess.user_id == user_id,
                EmailAccount.is_active == True,  # noqa: E712
            )
            .order_by(EmailAccount.name.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_all_user_authorized_accounts(
        db: AsyncSession,
        user_id: int,
    ) -> List[EmailAccount]:
        """Fetch all email accounts the user is authorized to access across all companies."""
        from sqlalchemy import or_
        from app.modules.companies.models import CompanyUser

        has_explicit_access = (
            select(EmailAccountAccess.id)
            .where(
                EmailAccountAccess.email_account_id == EmailAccount.id,
                EmailAccountAccess.user_id == user_id,
            )
            .exists()
        )

        is_company_admin = (
            select(CompanyUser.id)
            .where(
                CompanyUser.company_id == EmailAccount.company_id,
                CompanyUser.user_id == user_id,
                CompanyUser.role.in_([CompanyRole.OWNER.value, CompanyRole.ADMIN.value]),
            )
            .exists()
        )

        query = (
            select(EmailAccount)
            .where(
                EmailAccount.is_active == True,  # noqa: E712
                or_(has_explicit_access, is_company_admin),
            )
            .order_by(EmailAccount.name.asc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def grant_access(
        db: AsyncSession,
        account_id: int,
        user_id: int,
    ) -> Optional[EmailAccountAccess]:
        """Grant a company user access to an email account."""
        query = select(EmailAccountAccess).where(
            EmailAccountAccess.email_account_id == account_id,
            EmailAccountAccess.user_id == user_id,
        )
        existing = (await db.execute(query)).scalars().first()
        if existing:
            return None

        access = EmailAccountAccess(email_account_id=account_id, user_id=user_id)
        db.add(access)
        await db.commit()
        await db.refresh(access)
        return access

    @staticmethod
    async def revoke_access(
        db: AsyncSession,
        account_id: int,
        user_id: int,
    ) -> bool:
        """Revoke a user's access to an email account."""
        query = delete(EmailAccountAccess).where(
            EmailAccountAccess.email_account_id == account_id,
            EmailAccountAccess.user_id == user_id,
        )
        result = await db.execute(query)
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_access_list(
        db: AsyncSession,
        account_id: int,
    ) -> List[EmailAccountAccessRead]:
        """List all users who have explicit access to an email account."""
        query = (
            select(EmailAccountAccess)
            .options(selectinload(EmailAccountAccess.user))
            .where(EmailAccountAccess.email_account_id == account_id)
            .order_by(EmailAccountAccess.created_at.asc())
        )
        result = await db.execute(query)
        access_records = result.scalars().all()
        return [
            EmailAccountAccessRead(
                id=record.id,
                email_account_id=record.email_account_id,
                user_id=record.user_id,
                user_email=record.user.email,
                user_full_name=record.user.full_name,
                created_at=record.created_at,
            )
            for record in access_records
        ]

    @staticmethod
    async def get_company_access_list(
        db: AsyncSession,
        company_id: int,
    ) -> List[EmailAccountAccessRead]:
        """List all explicit user access permissions across all email accounts belonging to a company."""
        query = (
            select(EmailAccountAccess)
            .join(EmailAccount, EmailAccountAccess.email_account_id == EmailAccount.id)
            .options(selectinload(EmailAccountAccess.user))
            .where(EmailAccount.company_id == company_id)
            .order_by(EmailAccountAccess.created_at.asc())
        )
        result = await db.execute(query)
        access_records = result.scalars().all()
        return [
            EmailAccountAccessRead(
                id=record.id,
                email_account_id=record.email_account_id,
                user_id=record.user_id,
                user_email=record.user.email,
                user_full_name=record.user.full_name,
                created_at=record.created_at,
            )
            for record in access_records
        ]
