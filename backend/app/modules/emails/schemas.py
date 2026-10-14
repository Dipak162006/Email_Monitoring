from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from app.core.sanitizer import sanitize_html
from app.modules.emails.models import EmailDirection, EmailStatus


class EmailSendRequest(BaseModel):
    """Schema for sending an outgoing email message via an authorized email account."""
    model_config = ConfigDict(extra="forbid")

    email_account_id: int = Field(
        ...,
        description="Database ID of the company-owned EmailAccount to send from",
    )
    to: List[EmailStr] = Field(
        ...,
        min_length=1,
        description="One or more destination email addresses",
    )
    subject: str = Field(
        default="",
        max_length=998,
        description="Email subject line",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Plain text representation of the email message body",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Rich HTML representation of the email message body",
    )
    cc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional list of carbon copy (CC) recipients",
    )
    bcc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional list of blind carbon copy (BCC) recipients",
    )
    reply_to: Optional[EmailStr] = Field(
        default=None,
        description="Optional Reply-To header address",
    )
    in_reply_to: Optional[str] = Field(
        default=None,
        description="Optional Message-ID of parent email when replying",
    )
    thread_id: Optional[int] = Field(
        default=None,
        description="Optional conversation thread ID when replying",
    )
    signature_id: Optional[int] = Field(
        default=None,
        description="Optional EmailSignature ID to append to the message",
    )
    attachment_ids: Optional[List[int]] = Field(
        default=None,
        description="Optional list of pre-uploaded EmailAttachment IDs to attach to the message",
    )
    campaign_attachment_ids: Optional[List[int]] = Field(
        default=None,
        description="Optional list of CampaignAttachment IDs to attach to the message",
    )
    unsubscribe_url: Optional[str] = Field(
        default=None,
        description="Optional RFC 8058 one-click unsubscribe URL",
    )
    custom_headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional custom MIME headers to attach to the outgoing message",
    )

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def coerce_recipients_list(cls, value: Any) -> Any:
        """Allow a single string email address to be passed as a recipient list."""
        if isinstance(value, str):
            value = [value.strip()]
        return value

    @model_validator(mode="after")
    def validate_content_present(self) -> "EmailSendRequest":
        """Ensure either body_text or body_html has content."""
        has_text = bool(self.body_text and self.body_text.strip())
        has_html = bool(self.body_html and self.body_html.strip())
        if not has_text and not has_html:
            raise ValueError("At least one of body_text or body_html must be provided and non-empty.")
        return self


class EmailRead(BaseModel):
    """Safe schema for reading persisted email messages."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    email_account_id: int
    thread_id: Optional[int] = None
    user_id: Optional[int] = None
    message_id: Optional[str] = None
    imap_uid: Optional[str] = None
    in_reply_to: Optional[str] = None
    references_header: Optional[str] = None
    direction: EmailDirection
    status: EmailStatus
    sender: str
    recipients: List[str]
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    is_read: bool
    is_starred: bool
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Number of stored downloadable attachments linked to this email (0 when none)
    attachment_count: int = 0


class EmailSyncRequest(BaseModel):
    """Optional parameters for triggering an IMAP synchronization run."""
    model_config = ConfigDict(extra="forbid")

    folder: str = Field(default="INBOX", max_length=100, description="IMAP mailbox folder to synchronize")
    max_messages: int = Field(default=50, ge=1, le=500, description="Maximum number of recent messages to inspect")
    background: bool = Field(default=False, description="Whether to execute synchronization asynchronously via Celery")


class EmailSyncResult(BaseModel):
    """Summary of an IMAP mailbox synchronization operation."""
    model_config = ConfigDict(from_attributes=True)

    email_account_id: int
    status: str = Field(description="Overall sync status: SUCCESS, PARTIAL, or FAILED")
    folder: str = Field(description="Synchronized IMAP mailbox folder")
    total_discovered: int = Field(description="Number of messages inspected on the IMAP server")
    new_messages: int = Field(description="Number of new incoming emails parsed and stored")
    duplicates_skipped: int = Field(description="Number of already-existing emails skipped")
    malformed_skipped: int = Field(description="Number of malformed messages safely skipped")
    synced_at: datetime = Field(description="Timestamp when sync was executed")
    error_message: Optional[str] = Field(default=None, description="Safe error details if sync failed or had partial errors")
    task_id: Optional[str] = Field(default=None, description="Celery task identifier if executed in background")


class EmailSyncJobResponse(BaseModel):
    """Response returned when IMAP synchronization is queued as a background task."""
    model_config = ConfigDict(from_attributes=True)

    task_id: str = Field(description="Celery task identifier")
    status: str = Field(default="QUEUED", description="Current status of the background task")
    email_account_id: int = Field(description="Target email account identifier")
    folder: str = Field(default="INBOX", description="Target mailbox folder")
    message: str = Field(default="Email synchronization queued in background.", description="Status summary message")



class EmailThreadRead(BaseModel):
    """Summary representation of a conversation thread."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    email_account_id: int
    subject: str
    snippet: Optional[str] = None
    message_count: int
    has_reply: bool
    last_message_at: datetime
    is_read: bool
    created_at: datetime
    updated_at: datetime


class EmailThreadDetail(EmailThreadRead):
    """Detailed conversation thread including its chronologically ordered messages."""
    emails: List[EmailRead] = []


class ThreadListResponse(BaseModel):
    """Paginated list of conversation threads."""
    threads: List[EmailThreadRead]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# M8 Mailbox Schemas
# ---------------------------------------------------------------------------

VALID_FOLDERS = frozenset({"inbox", "sent", "drafts", "bounced", "responses", "trash"})


class EmailListResponse(BaseModel):
    """Paginated list of emails."""
    emails: List[EmailRead]
    total: int
    limit: int
    offset: int


class EmailReadUpdate(BaseModel):
    """Request body for explicitly setting an email's read/unread state."""
    model_config = ConfigDict(extra="forbid")

    is_read: bool = Field(..., description="Set to true to mark read, false to mark unread")


class EmailStarUpdate(BaseModel):
    """Request body for explicitly setting an email's starred/unstarred state."""
    model_config = ConfigDict(extra="forbid")

    is_starred: bool = Field(..., description="Set to true to star the email, false to unstar")


# ---------------------------------------------------------------------------
# M9 Compose and Draft Schemas
# ---------------------------------------------------------------------------

class EmailDraftCreate(BaseModel):
    """Schema for creating a work-in-progress draft email message."""
    model_config = ConfigDict(extra="forbid")

    email_account_id: int = Field(
        ...,
        description="Database ID of the company-owned EmailAccount to send from",
    )
    to: Optional[List[EmailStr]] = Field(
        default_factory=list,
        description="Optional list of destination email addresses (empty for new drafts)",
    )
    cc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional list of carbon copy (CC) recipients",
    )
    bcc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional list of blind carbon copy (BCC) recipients",
    )
    subject: Optional[str] = Field(
        default="",
        max_length=998,
        description="Email subject line",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Plain text representation of the draft body",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Rich HTML representation of the draft body",
    )
    reply_to: Optional[EmailStr] = Field(
        default=None,
        description="Optional Reply-To header address",
    )
    in_reply_to: Optional[str] = Field(
        default=None,
        description="Optional Message-ID of parent email when drafting a reply",
    )
    thread_id: Optional[int] = Field(
        default=None,
        description="Optional conversation thread ID when drafting a reply",
    )
    signature_id: Optional[int] = Field(
        default=None,
        description="Optional EmailSignature ID to append to the draft",
    )

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def coerce_recipients_list(cls, value: Any) -> Any:
        """Allow a single string email address to be passed as a recipient list, and handle None."""
        if value is None:
            return []
        if isinstance(value, str):
            value = [value.strip()]
        return value


class EmailDraftUpdate(BaseModel):
    """Schema for updating an existing work-in-progress draft message."""
    model_config = ConfigDict(extra="forbid")

    email_account_id: Optional[int] = Field(
        default=None,
        description="Optional new EmailAccount ID to switch the From address",
    )
    to: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional updated list of destination email addresses",
    )
    cc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional updated list of carbon copy (CC) recipients",
    )
    bcc: Optional[List[EmailStr]] = Field(
        default=None,
        description="Optional updated list of blind carbon copy (BCC) recipients",
    )
    subject: Optional[str] = Field(
        default=None,
        max_length=998,
        description="Optional updated email subject line",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Optional updated plain text body",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Optional updated rich HTML body",
    )
    reply_to: Optional[EmailStr] = Field(
        default=None,
        description="Optional updated Reply-To header address",
    )
    in_reply_to: Optional[str] = Field(
        default=None,
        description="Optional updated Message-ID of parent email",
    )
    thread_id: Optional[int] = Field(
        default=None,
        description="Optional updated conversation thread ID",
    )
    signature_id: Optional[int] = Field(
        default=None,
        description="Optional EmailSignature ID to apply to the draft",
    )

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def coerce_recipients_list(cls, value: Any) -> Any:
        """Allow a single string email address to be passed as a recipient list."""
        if value is None:
            return None
        if isinstance(value, str):
            value = [value.strip()]
        return value


# -----------------------------------------------------------------------------
# M10 Email Templates Schemas
# -----------------------------------------------------------------------------

class EmailTemplateCreate(BaseModel):
    """Schema for creating a reusable email template."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the template",
    )
    subject: Optional[str] = Field(
        default="",
        max_length=998,
        description="Template email subject line",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Plain text representation of the template body",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Rich HTML representation of the template body",
    )
    email_account_id: Optional[int] = Field(
        default=None,
        description="Optional EmailAccount ID if template is scoped to an account",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the template is active and usable",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Template name cannot be empty or whitespace.")
        return stripped


class EmailTemplateUpdate(BaseModel):
    """Schema for updating an existing email template."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated template name",
    )
    subject: Optional[str] = Field(
        default=None,
        max_length=998,
        description="Updated template email subject line",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Updated plain text body",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Updated rich HTML body",
    )
    email_account_id: Optional[int] = Field(
        default=None,
        description="Updated EmailAccount ID",
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="Updated active status",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Template name cannot be empty or whitespace.")
            return stripped
        return v


class EmailTemplateActiveToggle(BaseModel):
    """Schema for toggling template active status."""
    model_config = ConfigDict(extra="forbid")

    is_active: bool = Field(
        ...,
        description="Active status of the template",
    )


class EmailTemplateRead(BaseModel):
    """Safe schema for reading persisted email templates."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    email_account_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmailTemplateListResponse(BaseModel):
    """Paginated list response of email templates."""
    templates: List[EmailTemplateRead]
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# M11 Email Signatures Schemas
# -----------------------------------------------------------------------------

class EmailSignatureCreate(BaseModel):
    """Schema for creating a new email signature."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Friendly name for the signature",
    )
    email_account_id: Optional[int] = Field(
        default=None,
        description="Associated EmailAccount ID (required if not provided in URL path)",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Plain-text representation of the email signature",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Rich HTML representation of the email signature",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this signature is the default for the associated account",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Signature name cannot be empty or whitespace.")
        return stripped

    @field_validator("body_html")
    @classmethod
    def validate_body_html(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_html(v)
        return v


class EmailSignatureUpdate(BaseModel):
    """Schema for updating an existing email signature."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated friendly name for the signature",
    )
    email_account_id: Optional[int] = Field(
        default=None,
        description="Optionally reassign to another EmailAccount in the same company",
    )
    body_text: Optional[str] = Field(
        default=None,
        description="Updated plain-text representation of the signature",
    )
    body_html: Optional[str] = Field(
        default=None,
        description="Updated rich HTML representation of the signature",
    )
    is_default: Optional[bool] = Field(
        default=None,
        description="Set or unset default signature status for the associated account",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Signature name cannot be empty or whitespace.")
            return stripped
        return v

    @field_validator("body_html")
    @classmethod
    def validate_body_html(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_html(v)
        return v


class EmailSignatureRead(BaseModel):
    """Safe schema for reading persisted email signatures."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    email_account_id: int
    user_id: Optional[int] = None
    name: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class EmailSignatureListResponse(BaseModel):
    """Paginated list response of email signatures."""
    signatures: List[EmailSignatureRead]
    total: int
    limit: int
    offset: int


class EmailSignatureCopyRequest(BaseModel):
    """Schema for copying an email signature to another email account."""
    model_config = ConfigDict(extra="forbid")

    target_email_account_id: int = Field(
        ...,
        description="Destination EmailAccount ID within the same company",
    )
    new_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional custom name for the copied signature",
    )
    make_default: bool = Field(
        default=False,
        description="Whether to make the copied signature default on the destination account",
    )


# Schema Aliases
SignatureCreate = EmailSignatureCreate
SignatureUpdate = EmailSignatureUpdate
SignatureRead = EmailSignatureRead
SignatureCopyRequest = EmailSignatureCopyRequest
SignatureListResponse = EmailSignatureListResponse


# -----------------------------------------------------------------------------
# M12 Email Attachments Schemas
# -----------------------------------------------------------------------------

class EmailAttachmentRead(BaseModel):
    """Safe schema for reading email attachment metadata."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    email_account_id: int
    email_id: int
    file_name: str
    content_type: str
    file_size: int
    created_at: datetime
    updated_at: datetime


class EmailAttachmentListResponse(BaseModel):
    """List response of email attachments."""
    attachments: List[EmailAttachmentRead]
    total: int


# Schema Aliases
AttachmentRead = EmailAttachmentRead
AttachmentListResponse = EmailAttachmentListResponse


# -----------------------------------------------------------------------------
# Dashboard & Email Analytics Schemas
# -----------------------------------------------------------------------------

class DashboardStatsResponse(BaseModel):
    """Aggregated email monitoring statistics with period comparisons."""
    model_config = ConfigDict(from_attributes=True)

    sent_count: int = Field(description="Total outgoing emails sent in the selected period")
    bounced_count: int = Field(description="Total bounced emails in the selected period")
    response_count: int = Field(description="Total customer response emails in the selected period")
    bounce_rate: float = Field(description="Bounce rate percentage (bounced / sent * 100)")
    sent_change_percent: Optional[float] = Field(default=None, description="Percentage change in sent emails vs previous equivalent period")
    bounced_change_percent: Optional[float] = Field(default=None, description="Percentage change in bounced emails vs previous equivalent period")
    response_change_percent: Optional[float] = Field(default=None, description="Percentage change in response volume vs previous equivalent period")
    period_start: Optional[datetime] = Field(default=None, description="Start timestamp of the analyzed period")
    period_end: Optional[datetime] = Field(default=None, description="End timestamp of the analyzed period")


class DashboardActivityPoint(BaseModel):
    """Daily activity volume point for email trends chart."""
    date: str = Field(description="Date string in YYYY-MM-DD format")
    label: str = Field(description="Display label, e.g. 'Mon', 'Tue', 'Fri'")
    sent: int = Field(default=0, description="Number of sent emails on this day")
    responses: int = Field(default=0, description="Number of incoming replies on this day")
    bounced: int = Field(default=0, description="Number of bounced emails on this day")


class DashboardActivityResponse(BaseModel):
    """Time-series activity trends for the selected date range."""
    points: List[DashboardActivityPoint] = Field(default_factory=list)
    total_sent: int = Field(default=0)
    total_responses: int = Field(default=0)
    total_bounced: int = Field(default=0)


class AccountHealthItem(BaseModel):
    """Health and status indicator for a connected email account."""
    id: int
    name: str
    email_address: str
    provider: str
    is_active: bool
    last_synced_at: Optional[datetime] = None
    status_label: str = Field(description="Status indicator label: 'Operational', 'Syncing', or 'Idle'")


class AccountHealthResponse(BaseModel):
    """Overview of connected email accounts health and synchronization states."""
    total_accounts: int = Field(default=0)
    active_accounts: int = Field(default=0)
    syncing_accounts: int = Field(default=0)
    last_synced_at: Optional[datetime] = None
    accounts: List[AccountHealthItem] = Field(default_factory=list)


class MailboxCountsResponse(BaseModel):
    """Aggregated real-time counts across mailbox folders and unread telemetry."""
    inbox: int = Field(default=0, description="Total active incoming received emails")
    unread: int = Field(default=0, description="Total active unread incoming emails in inbox")
    sent: int = Field(default=0, description="Total active outgoing sent emails")
    drafts: int = Field(default=0, description="Total active outgoing draft emails")
    responses: int = Field(default=0, description="Total active customer replies in replied threads")
    bounced: int = Field(default=0, description="Total active bounced delivery failures")
    trash: int = Field(default=0, description="Total soft-deleted emails in trash")

