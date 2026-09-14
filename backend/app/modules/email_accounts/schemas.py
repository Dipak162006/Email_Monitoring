from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.modules.email_accounts.models import EmailProvider, SecurityMode


class EmailAccountBase(BaseModel):
    """Base fields shared across email account operations."""
    name: str = Field(min_length=1, max_length=255, description="Descriptive display name (e.g. Sales, Support)")
    email_address: EmailStr = Field(description="Account email address")
    provider: EmailProvider = Field(default=EmailProvider.CUSTOM, description="Provider type")

    # SMTP Configuration
    smtp_host: Optional[str] = Field(default=None, max_length=255)
    smtp_port: Optional[int] = Field(default=587)
    smtp_security: Optional[SecurityMode] = Field(default=SecurityMode.STARTTLS)
    smtp_username: Optional[str] = Field(default=None, max_length=255)

    # IMAP Configuration
    imap_host: Optional[str] = Field(default=None, max_length=255)
    imap_port: Optional[int] = Field(default=993)
    imap_security: Optional[SecurityMode] = Field(default=SecurityMode.SSL)
    imap_username: Optional[str] = Field(default=None, max_length=255)


class EmailAccountCreate(EmailAccountBase):
    """Payload for creating a new company email account."""
    smtp_password: Optional[str] = Field(default=None, description="Plaintext SMTP password (encrypted at rest)")
    imap_password: Optional[str] = Field(default=None, description="Plaintext IMAP password (encrypted at rest)")


class EmailAccountUpdate(BaseModel):
    """Payload for updating an existing company email account."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email_address: Optional[EmailStr] = None
    provider: Optional[EmailProvider] = None

    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_security: Optional[SecurityMode] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = Field(default=None, description="New SMTP password (will update encrypted store)")

    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_security: Optional[SecurityMode] = None
    imap_username: Optional[str] = None
    imap_password: Optional[str] = Field(default=None, description="New IMAP password (will update encrypted store)")

    is_active: Optional[bool] = None


class EmailAccountRead(BaseModel):
    """Public representation of an email account (credentials NEVER returned)."""
    id: int
    company_id: int
    name: str
    email_address: str
    provider: EmailProvider

    # SMTP Metadata
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_security: Optional[SecurityMode] = None
    smtp_username: Optional[str] = None
    has_smtp_password: bool = Field(description="Indicates whether an SMTP password is encrypted and stored")

    # IMAP Metadata
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_security: Optional[SecurityMode] = None
    imap_username: Optional[str] = None
    has_imap_password: bool = Field(description="Indicates whether an IMAP password is encrypted and stored")

    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailAccountAccessRead(BaseModel):
    """Representation of an access permission record for an email account."""
    id: int
    email_account_id: int
    user_id: int
    user_email: str
    user_full_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailAccountAccessGrant(BaseModel):
    """Payload for granting a company user access to an email account."""
    user_id: int = Field(description="ID of user who must be a verified company member")
