from typing import Optional
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyUser
from app.modules.recipient_lists.schemas import (
    RecipientListCreate,
    RecipientListImportResponse,
    RecipientListMemberCreate,
    RecipientListMemberPaginationResponse,
    RecipientListMemberResponse,
    RecipientListMemberUpdate,
    RecipientListPaginationResponse,
    RecipientListResponse,
    RecipientListUpdate,
)
from app.modules.recipient_lists.service import RecipientListService

router = APIRouter(
    prefix="/companies/{company_id}/recipient-lists",
    tags=["Recipient Lists"],
)


# ---------------------------------------------------------------------------
# Recipient List Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=RecipientListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new recipient list for a company (Admin/Owner only)",
)
@router.post(
    "/",
    response_model=RecipientListResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_recipient_list(
    company_id: int,
    list_in: RecipientListCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> RecipientListResponse:
    """Create a new reusable recipient list under the given company."""
    return await RecipientListService.create_list(
        db=db,
        company_id=company_id,
        list_in=list_in,
        user_id=membership.user_id,
    )


@router.get(
    "",
    response_model=RecipientListPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List recipient lists for a company with pagination and search",
)
@router.get(
    "/",
    response_model=RecipientListPaginationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_recipient_lists(
    company_id: int,
    search: Optional[str] = Query(None, description="Search term for list name or description"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> RecipientListPaginationResponse:
    """List all recipient lists belonging to the company."""
    items, total = await RecipientListService.list_lists(
        db=db,
        company_id=company_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return RecipientListPaginationResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{list_id}",
    response_model=RecipientListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific recipient list",
)
async def get_recipient_list(
    company_id: int,
    list_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> RecipientListResponse:
    """Retrieve metadata and contact count for a specific recipient list."""
    return await RecipientListService.get_list(
        db=db,
        company_id=company_id,
        list_id=list_id,
    )


@router.patch(
    "/{list_id}",
    response_model=RecipientListResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a recipient list (Admin/Owner only)",
)
async def update_recipient_list(
    company_id: int,
    list_id: int,
    list_in: RecipientListUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> RecipientListResponse:
    """Update name or description of an existing recipient list."""
    return await RecipientListService.update_list(
        db=db,
        company_id=company_id,
        list_id=list_id,
        list_in=list_in,
    )


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a recipient list (Admin/Owner only)",
)
async def delete_recipient_list(
    company_id: int,
    list_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a recipient list and all its members. Does not impact campaign history."""
    await RecipientListService.delete_list(
        db=db,
        company_id=company_id,
        list_id=list_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Recipient List Member Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{list_id}/members",
    response_model=RecipientListMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a contact member to a recipient list (Admin/Owner only)",
)
@router.post(
    "/{list_id}/members/",
    response_model=RecipientListMemberResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def add_list_member(
    company_id: int,
    list_id: int,
    member_in: RecipientListMemberCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> RecipientListMemberResponse:
    """Add a single recipient member to a list. Rejects duplicate emails within the list."""
    return await RecipientListService.add_member(
        db=db,
        company_id=company_id,
        list_id=list_id,
        member_in=member_in,
    )


@router.get(
    "/{list_id}/members",
    response_model=RecipientListMemberPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List members of a recipient list with pagination and search",
)
@router.get(
    "/{list_id}/members/",
    response_model=RecipientListMemberPaginationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_list_members(
    company_id: int,
    list_id: int,
    search: Optional[str] = Query(None, description="Search term for email or name"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> RecipientListMemberPaginationResponse:
    """Retrieve contacts belonging to a specific recipient list."""
    items, total = await RecipientListService.list_members(
        db=db,
        company_id=company_id,
        list_id=list_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return RecipientListMemberPaginationResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{list_id}/members/{member_id}",
    response_model=RecipientListMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific member",
)
async def get_list_member(
    company_id: int,
    list_id: int,
    member_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> RecipientListMemberResponse:
    """Retrieve a single member from a recipient list."""
    return await RecipientListService.get_member(
        db=db,
        company_id=company_id,
        list_id=list_id,
        member_id=member_id,
    )


@router.patch(
    "/{list_id}/members/{member_id}",
    response_model=RecipientListMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a list member (Admin/Owner only)",
)
async def update_list_member(
    company_id: int,
    list_id: int,
    member_id: int,
    member_in: RecipientListMemberUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> RecipientListMemberResponse:
    """Update email, first name, or last name of an existing member."""
    return await RecipientListService.update_member(
        db=db,
        company_id=company_id,
        list_id=list_id,
        member_id=member_id,
        member_in=member_in,
    )


@router.delete(
    "/{list_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from a recipient list (Admin/Owner only)",
)
async def remove_list_member(
    company_id: int,
    list_id: int,
    member_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a contact from a recipient list."""
    await RecipientListService.remove_member(
        db=db,
        company_id=company_id,
        list_id=list_id,
        member_id=member_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{list_id}/members/import",
    response_model=RecipientListImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import contacts from a CSV file into a recipient list (Admin/Owner only)",
)
@router.post(
    "/{list_id}/members/import/",
    response_model=RecipientListImportResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def import_list_members_csv(
    company_id: int,
    list_id: int,
    file: UploadFile = File(..., description="CSV file with email, first_name, last_name headers"),
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> RecipientListImportResponse:
    """Import recipient members from an uploaded CSV file.
    
    Expected CSV columns: email (required), first_name (optional), last_name (optional).
    Normalizes email, detects in-file duplicates and in-list database duplicates,
    and transactionally inserts valid contacts.
    Requires OWNER or ADMIN role in the company.
    """
    return await RecipientListService.import_members_csv(
        db=db,
        company_id=company_id,
        list_id=list_id,
        file=file,
    )
