from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyUser
from app.modules.campaigns.schemas import (
    SuppressionBulkCreateRequest,
    SuppressionBulkCreateResponse,
    SuppressionCreate,
    SuppressionRead,
)
from app.modules.campaigns.suppression_service import SuppressionService

router = APIRouter(prefix="/companies/{company_id}/suppressions", tags=["Campaign Suppressions"])


@router.post(
    "",
    response_model=SuppressionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add an email to company suppression list (Admin/Owner only)",
)
@router.post(
    "/",
    response_model=SuppressionRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_suppression(
    company_id: int,
    suppression_in: SuppressionCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> SuppressionRead:
    """Manually add an email to the company-wide suppression list.
    
    Requires OWNER or ADMIN role in the company.
    Normalizes email, checks company uniqueness, and returns 409 if already suppressed.
    """
    entry = await SuppressionService.create_suppression(
        db=db,
        company_id=company_id,
        suppression_in=suppression_in,
    )
    return SuppressionRead.model_validate(entry)


@router.post(
    "/bulk",
    response_model=SuppressionBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk add emails to company suppression list (Admin/Owner only)",
)
async def bulk_create_suppressions(
    company_id: int,
    bulk_in: SuppressionBulkCreateRequest,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> SuppressionBulkCreateResponse:
    """Bulk add email addresses to the company suppression list with batch deduplication.
    
    Requires OWNER or ADMIN role in the company.
    """
    return await SuppressionService.bulk_create_suppressions(
        db=db,
        company_id=company_id,
        bulk_in=bulk_in,
    )


@router.get(
    "",
    response_model=List[SuppressionRead],
    status_code=status.HTTP_200_OK,
    summary="List suppressed emails for a company",
)
@router.get(
    "/",
    response_model=List[SuppressionRead],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_suppressions(
    company_id: int,
    reason: Optional[str] = Query(None, description="Filter by suppression reason (BOUNCE, UNSUBSCRIBE, MANUAL, COMPLAINT)"),
    search: Optional[str] = Query(None, description="Search by email substring"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> List[SuppressionRead]:
    """List suppressed email addresses for the company.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    """
    entries = await SuppressionService.list_suppressions(
        db=db,
        company_id=company_id,
        reason=reason,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [SuppressionRead.model_validate(e) for e in entries]


@router.get(
    "/{suppression_id}",
    response_model=SuppressionRead,
    status_code=status.HTTP_200_OK,
    summary="Get suppression entry details",
)
async def get_suppression(
    company_id: int,
    suppression_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> SuppressionRead:
    """Retrieve details of a specific suppression entry.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    Returns 404 for cross-company access (anti-enumeration).
    """
    entry = await SuppressionService.get_suppression(
        db=db,
        company_id=company_id,
        suppression_id=suppression_id,
    )
    return SuppressionRead.model_validate(entry)


@router.delete(
    "/{suppression_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an email from company suppression list (Admin/Owner only)",
)
async def delete_suppression(
    company_id: int,
    suppression_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a suppression entry from the company suppression list.
    
    Requires OWNER or ADMIN role in the company.
    Returns 404 for cross-company access.
    """
    await SuppressionService.delete_suppression(
        db=db,
        company_id=company_id,
        suppression_id=suppression_id,
    )
