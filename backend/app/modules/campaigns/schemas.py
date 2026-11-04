from app.modules.campaigns.window_service import SendingWindowConfig
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


TAG_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def normalize_and_validate_tag(tag: str) -> str:
    """Normalize and validate a single recipient tag.
    
    Trims whitespace, lowercases, verifies length 1..50 and allowed characters.
    Allowed characters: alphanumeric, underscores, hyphens, and dots.
    """
    if not isinstance(tag, str):
        raise ValueError("Tag must be a string.")
    normalized = tag.strip().lower()
    if not normalized:
        raise ValueError("Tag cannot be empty or whitespace only.")
    if len(normalized) > 50:
        raise ValueError(f"Tag '{normalized}' exceeds maximum length of 50 characters.")
    if not TAG_REGEX.match(normalized):
        raise ValueError(
            f"Invalid tag '{normalized}'. Tags may only contain letters, numbers, hyphens, underscores, and dots."
        )
    return normalized


def normalize_and_validate_tag_list(tags: Optional[List[str]]) -> List[str]:
    """Normalize, validate, and deduplicate a list of tags while preserving order."""
    if not tags:
        return []
    result: List[str] = []
    seen = set()
    for item in tags:
        norm = normalize_and_validate_tag(item)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


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
# Campaign Step Schemas (C13)
# =============================================================================

class CampaignStepWrite(BaseModel):
    step_number: int = Field(..., ge=2, le=10, description="Follow-up step number (2..10)")
    delay_hours: int = Field(default=72, ge=1, le=720, description="Wait time in hours after previous step if no reply")
    subject: Optional[str] = Field(default="", max_length=255, description="Follow-up subject (if empty, defaults to Re: <Campaign Subject>)")
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    target_tags: Optional[List[str]] = Field(default_factory=list, description="Optional recipient tags to target for this step")
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")

    @field_validator("body_html")
    @classmethod
    def sanitize_step_html(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_html(v) if v is not None else None

    @field_validator("target_tags")
    @classmethod
    def validate_target_tags(cls, v: Optional[List[str]]) -> List[str]:
        return normalize_and_validate_tag_list(v)


class CampaignStepRead(BaseModel):
    id: int
    campaign_id: int
    step_number: int
    delay_hours: int
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    target_tags: List[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("target_tags", mode="before")
    @classmethod
    def coerce_target_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


# =============================================================================
# Campaign Schemas (C2 & C12 & C13)
# =============================================================================

class CampaignCreate(BaseModel):
    """Request schema for creating a new campaign in DRAFT state."""
    name: str = Field(..., min_length=1, max_length=255, description="Campaign display name")
    email_account_id: int = Field(..., description="ID of company-owned EmailAccount to send from")
    subject: str = Field(default="", max_length=998, description="Email subject line")
    body_text: Optional[str] = Field(default=None, description="Plaintext email body")
    body_html: Optional[str] = Field(default=None, description="HTML email body")
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="Optional scheduled launch time (UTC)",
    )
    send_interval_seconds: int = Field(
        default=0,
        ge=0,
        le=86400,
        description="Delay in seconds between consecutive recipient sends (0 = immediate, max 86400)",
    )
    followup_steps: Optional[List[CampaignStepWrite]] = Field(
        default=None,
        description="Optional list of automated follow-up steps (steps 2..10)",
    )
    sending_window: Optional[SendingWindowConfig] = Field(
        default=None,
        description="Optional sending window and timezone governance configuration",
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
    followup_steps: Optional[List[CampaignStepWrite]] = Field(
        default=None,
        description="Optional list of automated follow-up steps (steps 2..10)",
    )
    sending_window: Optional[SendingWindowConfig] = Field(
        default=None,
        description="Optional sending window and timezone governance configuration",
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
    steps: List[CampaignStepRead] = Field(default_factory=list)
    followup_steps: List[CampaignStepRead] = Field(default_factory=list)
    sending_window: Optional[SendingWindowConfig] = Field(
        default=None,
        description="Optional sending window and timezone governance configuration",
    )

    model_config = ConfigDict(from_attributes=True)



class CampaignSummaryCountsRead(BaseModel):
    """Company-wide campaign counts grouped by status for KPI summary cards."""
    total_count: int = 0
    active_count: int = 0
    scheduled_count: int = 0
    draft_count: int = 0
    completed_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CampaignDetailRead(CampaignRead):
    """Extended response schema for single-campaign retrieval."""
    email_account_name: Optional[str] = None
    email_account_address: Optional[str] = None
    pending_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    bounced_count: int = 0
    suppressed_count: int = 0
    replied_count: int = 0
    followup_scheduled_count: int = 0
    followup_sent_count: int = 0
    initial_sent_count: int = 0
    total_sent_count: int = 0
    unique_replied_count: int = 0

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
    tags: Optional[List[str]] = Field(default=None, description="Optional recipient tags")

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, v: str) -> str:
        return normalize_and_validate_email(v)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            return normalize_and_validate_tag_list(v)
        return None


class CampaignRecipientUpdate(BaseModel):
    """Request schema for updating an existing campaign recipient in a DRAFT campaign."""
    email: Optional[str] = Field(default=None, description="Updated recipient email address")
    first_name: Optional[str] = Field(default=None, max_length=100, description="Updated recipient first name")
    last_name: Optional[str] = Field(default=None, max_length=100, description="Updated recipient last name")
    custom_variables: Optional[Dict[str, Any]] = Field(default=None, description="Updated custom variables")
    tags: Optional[List[str]] = Field(default=None, description="Optional updated tags")

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return normalize_and_validate_email(v)
        return None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            return normalize_and_validate_tag_list(v)
        return None


class CampaignRecipientRead(BaseModel):
    """Response schema for a campaign recipient."""
    id: int
    campaign_id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    custom_variables: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    status: CampaignRecipientStatus
    current_step_number: int = 0
    next_step_due_at: Optional[datetime] = None
    stopped_reason: Optional[str] = None
    replied_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


class CampaignRecipientTagsUpdateRequest(BaseModel):
    """Request schema for replacing all tags of a recipient."""
    tags: List[str] = Field(..., description="List of tags to assign to the recipient")

    model_config = ConfigDict(extra="forbid")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        return normalize_and_validate_tag_list(v)


class CampaignRecipientTagAddRequest(BaseModel):
    """Request schema for adding a single tag to a recipient."""
    tag: str = Field(..., description="Tag to add to the recipient")

    model_config = ConfigDict(extra="forbid")

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        return normalize_and_validate_tag(v)


class CampaignRecipientRescheduleRequest(BaseModel):
    """Request schema for rescheduling a recipient's next follow-up step."""
    next_step_due_at: Optional[datetime] = Field(
        default=None,
        description="New scheduled timestamp in UTC or with timezone for the next follow-up step",
    )
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="Alias for next_step_due_at",
    )

    @model_validator(mode="after")
    def validate_timestamp(self) -> "CampaignRecipientRescheduleRequest":
        if self.next_step_due_at is None and self.scheduled_at is None:
            raise ValueError("next_step_due_at or scheduled_at must be provided.")
        if self.next_step_due_at is None:
            self.next_step_due_at = self.scheduled_at
        return self


class CampaignRecipientStopRequest(BaseModel):
    """Request schema for manually stopping future emails to a recipient."""
    reason: Optional[str] = Field(
        default="MANUAL",
        description="Optional reason for stopping future sends to this recipient",
    )


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





# =============================================================================
# Campaign Analytics Funnel Schemas (M7)
# =============================================================================

class CampaignStepAnalytics(BaseModel):
    """Step-level conversion and outcome metrics derived from persisted delivery records."""
    step_id: int = Field(..., description="ID of the campaign step")
    step_number: int = Field(..., description="1-based step sequence number")
    subject: str = Field(..., description="Subject line for this step")
    delay_hours: int = Field(..., description="Delay hours relative to previous step")
    target_tags: List[str] = Field(default_factory=list, description="Target recipient tags configured for this step")
    targeted_count: int = Field(..., description="Number of campaign recipients targeted by this step's criteria")
    sent_count: int = Field(..., description="Number of deliveries dispatched with SENT status")
    sending_count: int = Field(default=0, description="Number of deliveries currently in SENDING status")
    bounced_count: int = Field(..., description="Number of deliveries marked BOUNCED or with bounced_at timestamp")
    failed_count: int = Field(default=0, description="Number of deliveries marked FAILED")
    skipped_count: int = Field(..., description="Number of deliveries SKIPPED due to manual action or tag non-match")
    replied_count: int = Field(..., description="Number of recipients whose reply was elicited by this step")
    pending_count: int = Field(..., description="Number of recipients queued or waiting to receive this step")
    delivered_count: int = Field(default=0, description="Estimated net delivered count (sent_count - bounced_count); actual mailbox receipt is not tracked")
    delivery_rate: float = Field(..., description="Estimated net delivery rate percentage ((sent_count - bounced_count) / sent_count * 100)")
    reply_rate: float = Field(..., description="Percentage of sent recipients who replied (replied_count / sent_count * 100)")
    bounce_rate: float = Field(..., description="Percentage of sent recipients who bounced (bounced_count / sent_count * 100)")

    model_config = ConfigDict(from_attributes=True)


class CampaignDeliveryTrendPoint(BaseModel):
    """Daily delivery volume and outcome data point derived from actual delivery records."""
    date: str = Field(..., description="Date of dispatch in YYYY-MM-DD format")
    sent_count: int = Field(default=0, description="Number of emails dispatched on this date")
    bounced_count: int = Field(default=0, description="Number of deliveries marked bounced on this date")
    replied_count: int = Field(default=0, description="Number of unique replying recipients recorded on this date")

    model_config = ConfigDict(from_attributes=True)


class CampaignAnalyticsResponse(BaseModel):
    """Campaign-level and per-step analytics funnel response."""
    campaign_id: int = Field(..., description="ID of the campaign")
    campaign_name: str = Field(..., description="Name of the campaign")
    campaign_status: str = Field(..., description="Lifecycle status of the campaign")
    total_recipients: int = Field(..., description="Total recipients attached to the campaign")
    total_steps: int = Field(..., description="Total steps configured for the campaign")
    initial_sent_count: int = Field(default=0, description="Total initial (Step 1) emails sent")
    followup_sent_count: int = Field(default=0, description="Total follow-up (Step 2+) emails sent")
    total_sent_count: int = Field(default=0, description="Total emails sent across all steps (initial + follow-up)")
    unique_replied_count: int = Field(default=0, description="Total unique recipients who replied to the campaign")
    steps: List[CampaignStepAnalytics] = Field(default_factory=list, description="Ordered per-step funnel analytics")
    delivery_trend: List["CampaignDeliveryTrendPoint"] = Field(
        default_factory=list,
        description="Chronological daily delivery activity aggregated from persisted delivery records",
    )
    omitted_metrics_notice: Optional[str] = Field(
        default="Open and click tracking metrics are omitted because the system does not record tracking pixels or link wraps.",
        description="Explanation for why open and click tracking metrics cannot be derived from stored data",
    )

    model_config = ConfigDict(from_attributes=True)


class CampaignDrilldownSummary(BaseModel):
    """Summary status counts for the unified drill-down page."""
    recipients_count: int = 0
    sent_count: int = 0
    replies_count: int = 0
    bounced_count: int = 0
    failed_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CampaignEmailsDrilldownItem(BaseModel):
    """Single record representing a recipient, sent email, reply, bounce, or failed delivery."""
    id: Union[int, str]
    recipient_id: Optional[int] = None
    delivery_id: Optional[int] = None
    email_id: Optional[int] = None
    thread_id: Optional[int] = None
    email: Optional[str] = None
    recipient_name: Optional[str] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    status: Optional[str] = None
    stopped_reason: Optional[str] = None
    step_number: Optional[int] = None
    subject: Optional[str] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    bounced_at: Optional[datetime] = None
    bounce_type: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: Optional[int] = None
    is_suppressed: Optional[bool] = None
    suppression_reason: Optional[str] = None
    can_retry: Optional[bool] = None
    created_at: Optional[datetime] = None
    next_step_due_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CampaignEmailsDrilldownResponse(BaseModel):
    """Paginated drill-down response for Campaign Emails page."""
    campaign_id: int
    campaign_name: str
    selected_status: str
    summary: CampaignDrilldownSummary
    total: int
    limit: int
    offset: int
    items: List[CampaignEmailsDrilldownItem]

    model_config = ConfigDict(from_attributes=True)
