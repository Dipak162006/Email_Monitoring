from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.domains.models import Domain, DomainVerificationStatus
from app.modules.domains.schemas import DomainCreate, DomainUpdate, normalize_domain_name


class DomainService:
    """Service layer managing company sending domains."""

    @staticmethod
    async def get_domain_by_name(
        db: AsyncSession,
        company_id: int,
        domain_name: str,
    ) -> Optional[Domain]:
        """Retrieve a domain by company ID and normalized domain name."""
        result = await db.execute(
            select(Domain).where(
                Domain.company_id == company_id,
                Domain.domain_name == domain_name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_domain(
        db: AsyncSession,
        company_id: int,
        domain_in: DomainCreate,
    ) -> Domain:
        """Create a new domain for a company.
        
        Applies deterministic domain normalization and duplicate protection.
        Initial status defaults to PENDING. No DNS lookups are performed.
        """
        normalized_name = normalize_domain_name(domain_in.domain_name)

        # Application-level duplicate check
        existing = await DomainService.get_domain_by_name(db, company_id, normalized_name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domain '{normalized_name}' already exists in this company",
            )

        domain = Domain(
            company_id=company_id,
            domain_name=normalized_name,
            dkim_selector=domain_in.dkim_selector,
            verification_status=DomainVerificationStatus.PENDING.value,
            spf_status=DomainVerificationStatus.PENDING.value,
            dkim_status=DomainVerificationStatus.PENDING.value,
            dmarc_status=DomainVerificationStatus.PENDING.value,
            mx_status=DomainVerificationStatus.PENDING.value,
        )
        db.add(domain)

        try:
            await db.commit()
            await db.refresh(domain)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domain '{normalized_name}' already exists in this company",
            )

        return domain

    @staticmethod
    async def list_domains(
        db: AsyncSession,
        company_id: int,
    ) -> List[Domain]:
        """List all domains belonging strictly to the specified company."""
        result = await db.execute(
            select(Domain)
            .where(Domain.company_id == company_id)
            .order_by(Domain.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_domain(
        db: AsyncSession,
        company_id: int,
        domain_id: int,
    ) -> Domain:
        """Retrieve a specific domain within a company.
        
        Enforces company isolation: returns 404 if not found or belongs to another company.
        """
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
                detail="Domain not found",
            )
        return domain

    @staticmethod
    async def update_domain(
        db: AsyncSession,
        company_id: int,
        domain_id: int,
        domain_update: DomainUpdate,
    ) -> Domain:
        """Update domain configuration.
        
        Only dkim_selector may be updated. When updated, DKIM and overall verification
        statuses are reset to PENDING. No DNS lookups are performed.
        """
        domain = await DomainService.get_domain(db, company_id, domain_id)

        update_data = domain_update.model_dump(exclude_unset=True)
        if "dkim_selector" in update_data:
            new_selector = update_data["dkim_selector"]
            if new_selector != domain.dkim_selector:
                domain.dkim_selector = new_selector
                domain.dkim_status = DomainVerificationStatus.PENDING.value
                domain.verification_status = DomainVerificationStatus.PENDING.value
                try:
                    await db.commit()
                    await db.refresh(domain)
                except Exception:
                    await db.rollback()
                    raise

        return domain

    @staticmethod
    async def delete_domain(
        db: AsyncSession,
        company_id: int,
        domain_id: int,
    ) -> None:
        """Delete a domain record from a company."""
        domain = await DomainService.get_domain(db, company_id, domain_id)
        try:
            await db.delete(domain)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def verify_domain(
        db: AsyncSession,
        company_id: int,
        domain_id: int,
        resolver: Optional[object] = None,
    ) -> Domain:
        """Perform synchronous DNS verification for a domain and persist results.
        
        Orchestrates low-level DNS checks through the isolated DNS resolver service.
        Updates MX, SPF, DKIM, DMARC, and overall verification statuses along with
        last_checked_at and safe verification error summary.
        """
        from app.services.dns.resolver import DNSResolver, verify_domain_dns

        domain = await DomainService.get_domain(db, company_id, domain_id)
        dns_resolver = resolver if isinstance(resolver, DNSResolver) else None

        result = verify_domain_dns(
            domain_name=domain.domain_name,
            dkim_selector=domain.dkim_selector,
            resolver=dns_resolver,
        )

        domain.mx_status = result.mx_status
        domain.spf_status = result.spf_status
        domain.dkim_status = result.dkim_status
        domain.dmarc_status = result.dmarc_status
        domain.verification_status = result.verification_status
        domain.verification_error = result.verification_error
        domain.last_checked_at = result.last_checked_at

        try:
            await db.commit()
            await db.refresh(domain)
        except Exception:
            await db.rollback()
            raise
        return domain
