from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyUser
from app.modules.domains.schemas import DomainCreate, DomainRead, DomainUpdate
from app.modules.domains.service import DomainService

router = APIRouter(prefix="/companies/{company_id}/domains", tags=["Domains"])


@router.post(
    "",
    response_model=DomainRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new domain to a company (Admin/Owner only)",
)
@router.post(
    "/",
    response_model=DomainRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_domain(
    company_id: int,
    domain_in: DomainCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    """Create and register a sending domain under a company.
    
    Requires OWNER or ADMIN role in the company.
    Initial verification status defaults to PENDING. No DNS lookups are performed.
    """
    return await DomainService.create_domain(
        db=db,
        company_id=company_id,
        domain_in=domain_in,
    )


@router.get(
    "",
    response_model=List[DomainRead],
    status_code=status.HTTP_200_OK,
    summary="List all domains registered for a company",
)
@router.get(
    "/",
    response_model=List[DomainRead],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_domains(
    company_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> List[DomainRead]:
    """List all registered sending domains for the company.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    """
    return await DomainService.list_domains(
        db=db,
        company_id=company_id,
    )


@router.get(
    "/{domain_id}",
    response_model=DomainRead,
    status_code=status.HTTP_200_OK,
    summary="Get details for a specific domain",
)
async def get_domain(
    company_id: int,
    domain_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    """Retrieve details and DNS status for a specific domain in the company.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    Returns 404 if the domain does not exist or belongs to another company.
    """
    return await DomainService.get_domain(
        db=db,
        company_id=company_id,
        domain_id=domain_id,
    )


@router.patch(
    "/{domain_id}",
    response_model=DomainRead,
    status_code=status.HTTP_200_OK,
    summary="Update domain configuration (Admin/Owner only)",
)
async def update_domain(
    company_id: int,
    domain_id: int,
    domain_update: DomainUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    """Update domain configuration (e.g. DKIM selector).
    
    Requires OWNER or ADMIN role in the company.
    Domain name is immutable and cannot be updated.
    """
    return await DomainService.update_domain(
        db=db,
        company_id=company_id,
        domain_id=domain_id,
        domain_update=domain_update,
    )


@router.delete(
    "/{domain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a domain from a company (Admin/Owner only)",
)
async def delete_domain(
    company_id: int,
    domain_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a sending domain.
    
    Requires OWNER or ADMIN role in the company.
    Returns 404 if the domain does not exist or belongs to another company.
    """
    await DomainService.delete_domain(
        db=db,
        company_id=company_id,
        domain_id=domain_id,
    )


@router.post(
    "/{domain_id}/verify",
    response_model=DomainRead,
    status_code=status.HTTP_200_OK,
    summary="Trigger synchronous DNS verification for a domain (Admin/Owner only)",
)
async def verify_domain(
    company_id: int,
    domain_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> DomainRead:
    """Perform synchronous DNS checks for MX, SPF, DKIM, and DMARC.
    
    Requires OWNER or ADMIN role in the company.
    Returns 404 if the domain does not exist or belongs to another company.
    """
    return await DomainService.verify_domain(
        db=db,
        company_id=company_id,
        domain_id=domain_id,
    )

