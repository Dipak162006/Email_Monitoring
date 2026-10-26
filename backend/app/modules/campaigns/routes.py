from typing import List, Optional, Union
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.companies.dependencies import (
    get_company_membership,
    require_company_admin_or_owner,
)
from app.modules.companies.models import CompanyUser
from app.modules.campaigns.dispatch_service import CampaignDispatchService
from app.modules.campaigns.preflight_service import CampaignPreflightService
from app.modules.campaigns.recipient_service import CampaignRecipientService
from app.modules.campaigns.schemas import (
    CampaignAttachmentListResponse,
    CampaignAttachmentRead,
    CampaignCreate,
    CampaignDetailRead,
    CampaignDispatchResponse,
    CampaignImportDraftRequest,
    CampaignPreflightResponse,
    CampaignRead,
    CampaignRecipientBulkCreateRequest,
    CampaignRecipientBulkCreateResponse,
    CampaignRecipientCreate,
    CampaignRecipientImportResponse,
    CampaignRecipientRead,
    CampaignRecipientUpdate,
    CampaignScheduleRequest,
    CampaignUpdate,
)
from app.modules.campaigns.service import CampaignService
from app.modules.emails.dependencies import verify_user_can_send_from_account

router = APIRouter(prefix="/companies/{company_id}/campaigns", tags=["Campaigns"])


@router.post(
    "",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new campaign in DRAFT state (Admin/Owner only)",
)
@router.post(
    "/",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_campaign(
    company_id: int,
    campaign_in: CampaignCreate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Create a new campaign in DRAFT state.
    
    Requires OWNER or ADMIN role in the company.
    Validates company ownership and active state of the sender EmailAccount.
    """
    return await CampaignService.create_campaign(
        db=db,
        company_id=company_id,
        campaign_in=campaign_in,
        creator_user_id=current_user.id,
    )


@router.get(
    "",
    response_model=List[CampaignRead],
    status_code=status.HTTP_200_OK,
    summary="List campaigns for a company",
)
@router.get(
    "/",
    response_model=List[CampaignRead],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_campaigns(
    company_id: int,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> List[CampaignRead]:
    """List all campaigns belonging to the company.
    
    Accessible to all company members (MEMBER, ADMIN, OWNER).
    """
    return await CampaignService.list_campaigns(
        db=db,
        company_id=company_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{campaign_id}",
    response_model=CampaignDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get campaign details",
)
async def get_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetailRead:
    """Retrieve detailed information about a specific campaign.
    
    Accessible to all company members (MEMBER, ADMIN, OWNER).
    Returns 404 if the campaign does not exist or belongs to another company.
    """
    campaign = await CampaignService.get_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )
    status_counts = await CampaignService.get_recipient_status_counts(db, campaign_id)
    return CampaignService.to_detail_schema(campaign, status_counts=status_counts)


@router.patch(
    "/{campaign_id}",
    response_model=CampaignRead,
    status_code=status.HTTP_200_OK,
    summary="Update a draft campaign (Admin/Owner only)",
)
async def update_campaign(
    company_id: int,
    campaign_id: int,
    campaign_update: CampaignUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Update editable fields of a campaign.
    
    Only campaigns in DRAFT status may be updated.
    Requires OWNER or ADMIN role.
    """
    return await CampaignService.update_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        campaign_update=campaign_update,
    )


@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an eligible campaign (Admin/Owner only)",
)
async def delete_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a campaign in safe state (DRAFT, COMPLETED, CANCELLED, FAILED).
    
    Active campaigns (RUNNING, QUEUED, PAUSED) cannot be deleted directly.
    Requires OWNER or ADMIN role.
    """
    await CampaignService.delete_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )


@router.post(
    "/{campaign_id}/preflight",
    response_model=CampaignPreflightResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate campaign preflight eligibility (Admin/Owner only)",
)
async def preflight_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignPreflightResponse:
    """Evaluate whether the campaign and its recipients are eligible to proceed to execution.
    
    Strictly read-only; does not mutate campaigns, recipients, or deliveries.
    Requires OWNER or ADMIN role.
    """
    return await CampaignPreflightService.validate_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        current_user=current_user,
        user_role=membership.role,
    )


@router.post(
    "/{campaign_id}/schedule",
    response_model=CampaignRead,
    status_code=status.HTTP_200_OK,
    summary="Schedule or queue campaign for execution (Admin/Owner only)",
)
async def schedule_campaign(
    company_id: int,
    campaign_id: int,
    schedule_in: Optional[CampaignScheduleRequest] = None,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Schedule a campaign for future execution or queue immediately.
    
    Transitions:
    - With future scheduled_at: DRAFT -> SCHEDULED or SCHEDULED -> SCHEDULED (reschedule)
    - Without scheduled_at (send-now): DRAFT -> QUEUED
    
    Validates sender account authorization and active status.
    Requires OWNER or ADMIN role.
    """
    campaign = await CampaignService.get_campaign(db, company_id, campaign_id)

    # Verify user has sender authorization for the selected email account
    await verify_user_can_send_from_account(
        db=db,
        current_user=current_user,
        account_id=campaign.email_account_id,
        company_id=company_id,
    )

    scheduled_at = schedule_in.scheduled_at if schedule_in else None
    return await CampaignService.schedule_or_send_now(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        scheduled_at=scheduled_at,
    )


@router.post(
    "/{campaign_id}/dispatch",
    response_model=CampaignDispatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch a campaign for asynchronous execution (Admin/Owner only)",
)
async def dispatch_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignDispatchResponse:
    """Asynchronously dispatch a campaign for execution via the Celery execution pipeline.
    
    Performs:
    1. Tenant isolation and company ownership verification
    2. Admin/Owner role authorization check
    3. Campaign state eligibility check (DRAFT/SCHEDULED -> QUEUED)
    4. Preflight validation (must be eligible)
    5. Duplicate dispatch prevention under database row-lock
    6. Celery task enqueuing (primitive IDs only)
    
    Requires OWNER or ADMIN role in the company.
    """
    return await CampaignDispatchService.dispatch_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        current_user=current_user,
        user_role=membership.role,
    )


@router.post(
    "/{campaign_id}/pause",
    response_model=CampaignRead,
    status_code=status.HTTP_200_OK,
    summary="Pause a running campaign (Admin/Owner only)",
)
async def pause_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Pause an actively running campaign (RUNNING -> PAUSED).
    
    Requires OWNER or ADMIN role.
    """
    return await CampaignService.pause_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )


@router.post(
    "/{campaign_id}/resume",
    response_model=CampaignRead,
    status_code=status.HTTP_200_OK,
    summary="Resume a paused campaign (Admin/Owner only)",
)
async def resume_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Resume a paused campaign (PAUSED -> RUNNING).
    
    Requires OWNER or ADMIN role.
    """
    return await CampaignService.resume_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )


@router.post(
    "/{campaign_id}/cancel",
    response_model=CampaignRead,
    status_code=status.HTTP_200_OK,
    summary="Cancel a campaign (Admin/Owner only)",
)
async def cancel_campaign(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRead:
    """Cancel an active or scheduled campaign.
    
    Transitions: SCHEDULED, QUEUED, RUNNING, PAUSED -> CANCELLED.
    Requires OWNER or ADMIN role.
    """
    return await CampaignService.cancel_campaign(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )


# =============================================================================
# Campaign Recipient Endpoints (C3)
# =============================================================================

@router.post(
    "/{campaign_id}/recipients",
    response_model=Union[CampaignRecipientBulkCreateResponse, CampaignRecipientRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add single or multiple recipients to a draft campaign (Admin/Owner only)",
)
async def create_recipient(
    company_id: int,
    campaign_id: int,
    recipient_in: Union[CampaignRecipientBulkCreateRequest, CampaignRecipientCreate, List[CampaignRecipientCreate]],
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
):
    """Add one or multiple recipients to a campaign.
    
    Only permitted when campaign is in DRAFT status.
    Deduplicates normalized addresses and rejects or skips duplicates.
    Requires OWNER or ADMIN role in the company.
    """
    if isinstance(recipient_in, CampaignRecipientBulkCreateRequest):
        return await CampaignRecipientService.bulk_create_recipients(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            recipients_in=recipient_in.recipients,
        )
    elif isinstance(recipient_in, list):
        return await CampaignRecipientService.bulk_create_recipients(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            recipients_in=recipient_in,
        )
    else:
        return await CampaignRecipientService.create_recipient(
            db=db,
            company_id=company_id,
            campaign_id=campaign_id,
            recipient_in=recipient_in,
        )


@router.post(
    "/{campaign_id}/recipients/bulk",
    response_model=CampaignRecipientBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk add recipients to a draft campaign (Admin/Owner only)",
)
async def bulk_create_recipients(
    company_id: int,
    campaign_id: int,
    bulk_in: CampaignRecipientBulkCreateRequest,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRecipientBulkCreateResponse:
    """Add multiple recipients to a DRAFT campaign in bulk with deduplication."""
    return await CampaignRecipientService.bulk_create_recipients(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        recipients_in=bulk_in.recipients,
    )


@router.get(
    "/{campaign_id}/recipients",
    response_model=List[CampaignRecipientRead],
    status_code=status.HTTP_200_OK,
    summary="List recipients for a campaign",
)
async def list_recipients(
    company_id: int,
    campaign_id: int,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by recipient status"),
    search: Optional[str] = Query(None, description="Search by email substring"),
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> List[CampaignRecipientRead]:
    """List recipients belonging to the campaign with pagination and filtering.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    """
    return await CampaignRecipientService.list_recipients(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        status_filter=status_filter,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{campaign_id}/recipients/{recipient_id}",
    response_model=CampaignRecipientRead,
    status_code=status.HTTP_200_OK,
    summary="Get recipient details",
)
async def get_recipient(
    company_id: int,
    campaign_id: int,
    recipient_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> CampaignRecipientRead:
    """Retrieve details of a specific campaign recipient.
    
    Accessible to all authorized company members (MEMBER, ADMIN, OWNER).
    Returns 404 for cross-company or cross-campaign access.
    """
    return await CampaignRecipientService.get_recipient(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=recipient_id,
    )


@router.patch(
    "/{campaign_id}/recipients/{recipient_id}",
    response_model=CampaignRecipientRead,
    status_code=status.HTTP_200_OK,
    summary="Update a campaign recipient (Admin/Owner only)",
)
async def update_recipient(
    company_id: int,
    campaign_id: int,
    recipient_id: int,
    recipient_update: CampaignRecipientUpdate,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRecipientRead:
    """Update editable fields of a recipient in a DRAFT campaign.
    
    Requires OWNER or ADMIN role in the company.
    Rejects update if campaign is not in DRAFT status.
    """
    return await CampaignRecipientService.update_recipient(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=recipient_id,
        recipient_update=recipient_update,
    )


@router.delete(
    "/{campaign_id}/recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a campaign recipient (Admin/Owner only)",
)
async def delete_recipient(
    company_id: int,
    campaign_id: int,
    recipient_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a recipient from a DRAFT campaign.
    
    Requires OWNER or ADMIN role in the company.
    Rejects deletion if campaign is not in DRAFT status.
    """
    await CampaignRecipientService.delete_recipient(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        recipient_id=recipient_id,
    )


@router.post(
    "/{campaign_id}/recipients/import",
    response_model=CampaignRecipientImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import recipients from a CSV file (Admin/Owner only)",
)
async def import_recipients_csv(
    company_id: int,
    campaign_id: int,
    file: UploadFile = File(..., description="CSV file containing recipient rows with an 'email' header"),
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> CampaignRecipientImportResponse:
    """Import recipients from an uploaded CSV file into a DRAFT campaign.
    
    Expected CSV columns: email, first_name (optional), last_name (optional), custom_variables (optional).
    Normalizes email, deduplicates within CSV and DB, and transactionally inserts valid rows.
    Requires OWNER or ADMIN role in the company.
    """
    return await CampaignRecipientService.import_recipients_csv(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        file=file,
    )


# =============================================================================
# Campaign Attachments & Draft Import Endpoints (C12)
# =============================================================================

@router.post(
    "/{campaign_id}/attachments",
    response_model=CampaignAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a campaign (Admin/Owner only)",
)
async def upload_campaign_attachment(
    company_id: int,
    campaign_id: int,
    file: UploadFile = File(..., description="File to attach to the campaign"),
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignAttachmentRead:
    """Upload a file attachment and associate it with an editable DRAFT campaign.
    
    Requires OWNER or ADMIN role in the company.
    Validates file size (max 25MB) and disallowed extensions.
    """
    attachment = await CampaignService.upload_attachment(
        db=db,
        current_user=current_user,
        company_id=company_id,
        campaign_id=campaign_id,
        upload_file=file,
    )
    return CampaignAttachmentRead.model_validate(attachment)


@router.get(
    "/{campaign_id}/attachments",
    response_model=CampaignAttachmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List attachments for a campaign",
)
async def list_campaign_attachments(
    company_id: int,
    campaign_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
) -> CampaignAttachmentListResponse:
    """List all attachments associated with a campaign.
    
    Accessible to all company members.
    """
    items = await CampaignService.list_attachments(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
    )
    return CampaignAttachmentListResponse(
        attachments=[CampaignAttachmentRead.model_validate(i) for i in items],
        total=len(items),
    )


@router.delete(
    "/{campaign_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment from a campaign (Admin/Owner only)",
)
async def delete_campaign_attachment(
    company_id: int,
    campaign_id: int,
    attachment_id: int,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an attachment from an editable DRAFT campaign and cleans up storage.
    
    Requires OWNER or ADMIN role in the company.
    """
    await CampaignService.delete_attachment(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        attachment_id=attachment_id,
    )


@router.get(
    "/{campaign_id}/attachments/{attachment_id}/download",
    summary="Download a campaign attachment file",
)
async def download_campaign_attachment(
    company_id: int,
    campaign_id: int,
    attachment_id: int,
    membership: CompanyUser = Depends(get_company_membership),
    db: AsyncSession = Depends(get_db),
):
    """Download physical file content of an attachment belonging to an authorized campaign."""
    file_path, filename, content_type = await CampaignService.get_attachment_for_download(
        db=db,
        company_id=company_id,
        campaign_id=campaign_id,
        attachment_id=attachment_id,
    )
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=content_type,
    )


@router.post(
    "/{campaign_id}/import-draft",
    response_model=CampaignDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Import subject, body, and compatible attachments from an existing draft (Admin/Owner only)",
)
async def import_draft_into_campaign(
    company_id: int,
    campaign_id: int,
    payload: CampaignImportDraftRequest,
    membership: CompanyUser = Depends(require_company_admin_or_owner),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetailRead:
    """Import subject, body, and compatible attachments from an existing draft into a DRAFT campaign.
    
    Requires OWNER or ADMIN role in the company.
    Validates draft ownership, sender account alignment, and authorization.
    """
    campaign = await CampaignService.import_draft(
        db=db,
        current_user=current_user,
        company_id=company_id,
        campaign_id=campaign_id,
        draft_id=payload.draft_id,
    )
    status_counts = await CampaignService.get_recipient_status_counts(db, campaign_id)
    return CampaignService.to_detail_schema(campaign, status_counts=status_counts)


