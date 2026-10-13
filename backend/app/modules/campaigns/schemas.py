from datetime import datetime
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sanitizer import sanitize_html
from app.modules.campaigns.models import (
    CampaignRecipientStatus,
    CampaignStatus,
    SuppressionReason,
)

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def normalize_and_validate_email(email_raw: str) -> str:
    """Normalize and syntactically validate a recipient email address.
    
    Rules:
    1. Trim whitespace.
    2. Lowercase for case-insensitive deduplication and campaign identity.
    3. Reject empty addresses.
    4. Reject addresses longer than 255 characters.
    5. Validate RFC 5322 compatible syntax without performing external DNS lookups.
    """
    if not isinstance(email_raw, str):
        raise ValueError("Email must be a string")

    email = email_raw.strip().lower()
    if not email:
        raise ValueError("Email address cannot be empty")

    if len(email) > 255:
        raise ValueError("Email address exceeds maximum length of 255 characters")

    if not EMAIL_REGEX.match(email):
        raise ValueError(f"Invalid email address format: '{email_raw}'")

    return email


# =============================================================================
# Campaign Attachment Schemas (C12)
# =============================================================================

class CampaignAttachmentRead(BaseModel):
    """Response schema for a campaign attachment."""
    id: int
    campaign_id: int
    company_id: int
    email_account_id: int
    file_name: str
    content_type: str
    file_size: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignAttachmentListResponse(BaseModel):
    """Response schema for listing attachments of a campaign."""
    attachments: List[CampaignAttachmentRead]
    total: int


class CampaignImportDraftRequest(BaseModel):
    """Request schema for importing an existing draft email into a campaign."""
    draft_id: int = Field(..., description="ID of the draft email to import")

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Campaign Schemas (C2 & C12)
# =============================================================================

class CampaignCreate(BaseModel):
    """Request schema for creating a new campaign in DRAFT state."""
    name: str = Field(..., min_length=1, max_length=255, description="Campaign display name")
    email_account_id: int = Field(..., description="ID of company-owned EmailAccount to send from")
    subject: str = Field(default="", max_length=998, description="Email subject line")
    body_text: Optional[str] = Field(default=None, description="Plaintext email body")
    body_html: Optional[str] = Field(default=None, description="HTML email body")
    send_interval_seconds: int = Field(
        default=0,
        ge=0,
        le=86400,
        description="Delay in seconds between consecutive recipient sends (0 = immediate, max 86400)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("body_html")
    @classmethod
    def sanitize_campaign_html(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_html(v)
        return None

    @field_validator("send_interval_seconds", mode="before")
    @classmethod
    def validate_send_interval(cls, v: Any) -> Any:
        if v is None:
            return 0
        if isinstance(v, bool):
            raise ValueError("send_interval_seconds must be an integer, not a boolean")
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("send_interval_seconds must be a valid integer")
        if v < 0:
            raise ValueError("send_interval_seconds cannot be negative")
        if v > 86400:
            raise ValueError("send_interval_seconds cannot exceed 86400 seconds (24 hours)")
        return v


class CampaignUpdate(BaseModel):
    """Request schema for updating campaign configuration.
    
    Only DRAFT campaigns may be modified.
    Direct updates to status, started_at, completed_at, and created_by_user_id are strictly forbidden.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Campaign display name")
    email_account_id: Optional[int] = Field(default=None, description="ID of company-owned EmailAccount")
    subject: Optional[str] = Field(default=None, max_length=998, description="Email subject line")
    body_text: Optional[str] = Field(default=None, description="Plaintext email body")
    body_html: Optional[str] = Field(default=None, description="HTML email body")
    scheduled_at: Optional[datetime] = Field(default=None, description="Scheduled launch time")
    send_interval_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        le=86400,
        description="Delay in seconds between consecutive recipient sends (0 = immediate, max 86400)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("body_html")
    @classmethod
    def sanitize_campaign_html(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_html(v)
        return None

    @field_validator("send_interval_seconds", mode="before")
    @classmethod
    def validate_send_interval(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError("send_interval_seconds must be an integer, not a boolean")
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError("send_interval_seconds must be a valid integer")
        if v < 0:
            raise ValueError("send_interval_seconds cannot be negative")
        if v > 86400:
            raise ValueError("send_interval_seconds cannot exceed 86400 seconds (24 hours)")
        return v


class CampaignScheduleRequest(BaseModel):
    """Request schema for scheduling or queuing a campaign.
    
    If scheduled_at is provided, the campaign transitions to SCHEDULED.
    If scheduled_at is omitted or null, the campaign transitions to QUEUED (immediate launch).
    """
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="Optional future launch timestamp (UTC). If null/omitted, queues immediately.",
    )

    model_config = ConfigDict(extra="forbid")


class CampaignRead(BaseModel):
    """Response schema for campaign summary details."""
    id: int
    company_id: int
    email_account_id: int
    name: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    status: CampaignStatus
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    send_interval_seconds: int = 0
    next_send_at: Optional[datetime] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    recipient_count: int = 0
    attachments: List[CampaignAttachmentRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CampaignDetailRead(CampaignRead):
    """Extended response schema for single-campaign retrieval."""
    email_account_name: Optional[str] = None
    email_account_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Campaign Recipient Schemas (C3)
# =============================================================================

class CampaignRecipientCreate(BaseModel):
    """Request schema for creating a single campaign recipient."""
    email: str = Field(..., description="Recipient email address")
    first_name: Optional[str] = Field(default=None, max_length=100, description="Recipient first name")
    last_name: Optional[str] = Field(default=None, max_length=100, description="Recipient last name")
    custom_variables: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary merge tag custom variables")

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, v: str) -> str:
        return normalize_and_validate_email(v)


class CampaignRecipientUpdate(BaseModel):
    """Request schema for updating an existing campaign recipient in a DRAFT campaign."""
    email: Optional[str] = Field(default=None, description="Updated recipient email address")
    first_name: Optional[str] = Field(default=None, max_length=100, description="Updated recipient first name")
    last_name: Optional[str] = Field(default=None, max_length=100, description="Updated recipient last name")
    custom_variables: Optional[Dict[str, Any]] = Field(default=None, description="Updated custom variables")

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return normalize_and_validate_email(v)
        return None


class CampaignRecipientRead(BaseModel):
    """Response schema for a campaign recipient."""
    id: int
    campaign_id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    custom_variables: Optional[Dict[str, Any]] = None
    status: CampaignRecipientStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignRecipientBulkCreateRequest(BaseModel):
    """Request schema for adding multiple recipients in bulk."""
    recipients: List[CampaignRecipientCreate] = Field(
        ...,
        min_length=1,
        description="Non-empty list of recipients to add to the campaign",
    )

    model_config = ConfigDict(extra="forbid")


class CampaignRecipientBulkCreateResponse(BaseModel):
    """Response schema for bulk recipient creation."""
    total_submitted: int
    inserted_count: int
    skipped_count: int
    recipients: List[CampaignRecipientRead] = Field(default_factory=list)
    skipped_emails: List[str] = Field(default_factory=list)


class CampaignRecipientImportResponse(BaseModel):
    """Response schema for CSV recipient import."""
    total_rows: int
    inserted_count: int
    skipped_duplicates_count: int
    invalid_rows_count: int
    skipped_emails: List[str] = Field(default_factory=list)
    invalid_rows: List[Dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Campaign Suppression Schemas (C4)
# =============================================================================

class SuppressionCreate(BaseModel):
    """Request schema for creating a manual company suppression entry."""
    email: str = Field(..., description="Email address to suppress company-wide")
    reason: SuppressionReason = Field(
        default=SuppressionReason.MANUAL,
        description="Reason for suppression (BOUNCE, UNSUBSCRIBE, MANUAL, COMPLAINT)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, v: str) -> str:
        return normalize_and_validate_email(v)


class SuppressionRead(BaseModel):
    """Response schema for a company suppression entry."""
    id: int
    company_id: int
    email: str
    reason: SuppressionReason
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuppressionBulkCreateRequest(BaseModel):
    """Request schema for bulk creating company suppression entries."""
    emails: List[str] = Field(..., min_length=1, description="List of email addresses to suppress")
    reason: SuppressionReason = Field(
        default=SuppressionReason.MANUAL,
        description="Reason for suppression applied to all addresses in this batch",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("emails")
    @classmethod
    def validate_emails_list(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Email list cannot be empty")
        validated = []
        for e in v:
            validated.append(normalize_and_validate_email(e))
        return validated


class SuppressionBulkCreateResponse(BaseModel):
    """Response schema for bulk company suppression creation."""
    total_submitted: int
    inserted_count: int
    skipped_count: int
    entries: List[SuppressionRead] = Field(default_factory=list)
    skipped_emails: List[str] = Field(default_factory=list)


# =============================================================================
# Campaign Preflight Schemas (C5)
# =============================================================================

class PreflightIssue(BaseModel):
    """Validation issue discovered during campaign preflight."""
    code: str = Field(..., description="Machine-readable issue category or code")
    message: str = Field(..., description="Human-readable description of the issue")
    severity: str = Field(default="BLOCKING", description="Severity level: BLOCKING or WARNING")
    blocking: bool = Field(default=True, description="Whether this issue blocks campaign execution")

    model_config = ConfigDict(from_attributes=True)


class CampaignPreflightResponse(BaseModel):
    """Deterministic eligibility report returned by campaign preflight."""
    eligible: bool = Field(..., description="Whether the campaign is currently eligible to proceed to execution")
    campaign_id: int = Field(..., description="ID of the validated campaign")
    recipient_count: int = Field(..., description="Total count of recipients configured for the campaign")
    eligible_recipient_count: int = Field(..., description="Count of recipients eligible for delivery")
    suppressed_recipient_count: int = Field(..., description="Count of recipients excluded due to suppression")
    issues: List[PreflightIssue] = Field(default_factory=list, description="List of blocking and warning validation issues")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Campaign Dispatch Schemas (C7)
# =============================================================================

class CampaignDispatchResponse(BaseModel):
    """Response schema for asynchronous campaign dispatch."""
    campaign_id: int = Field(..., description="ID of the dispatched campaign")
    company_id: int = Field(..., description="ID of the company owning the campaign")
    status: CampaignStatus = Field(..., description="Current status of the campaign (QUEUED)")
    task_id: Optional[str] = Field(default=None, description="Celery background task ID if enqueued")
    dispatched_at: datetime = Field(..., description="Timestamp when the campaign was queued for dispatch")
    eligible_recipient_count: int = Field(..., description="Count of eligible recipients verified during preflight")
    total_recipient_count: int = Field(..., description="Total recipients configured for the campaign")

    model_config = ConfigDict(from_attributes=True)


