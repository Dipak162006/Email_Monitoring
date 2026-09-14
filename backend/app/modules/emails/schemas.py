from datetime import datetime
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
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
    user_id: Optional[int] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
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
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
