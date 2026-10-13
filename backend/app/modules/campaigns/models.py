from datetime import datetime
import enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.emails.models import Email, EmailThread


class CampaignStatus(str, enum.Enum):
    """Lifecycle statuses for marketing / outreach campaigns."""
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class CampaignRecipientStatus(str, enum.Enum):
    """Lifecycle statuses for a campaign recipient."""
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    SUPPRESSED = "SUPPRESSED"


class CampaignDeliveryStatus(str, enum.Enum):
    """Lifecycle statuses for an individual delivery dispatch."""
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class SuppressionReason(str, enum.Enum):
    """Reason why an email address is suppressed from future campaign deliveries."""
    BOUNCE = "BOUNCE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    MANUAL = "MANUAL"
    COMPLAINT = "COMPLAINT"


class Campaign(Base):
    """Campaign database model representing a structured email outreach sequence or broadcast.
    
    A campaign strictly belongs to a Company organization tenant and dispatches
    through a designated, authorized company EmailAccount.
    """
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("email_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(998), default="", nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(50),
        default=CampaignStatus.DRAFT.value,
        nullable=False,
        index=True,
    )

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    send_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    next_send_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    email_account: Mapped["EmailAccount"] = relationship("EmailAccount")
    created_by_user: Mapped[Optional["User"]] = relationship("User")
    recipients: Mapped[List["CampaignRecipient"]] = relationship(
        "CampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    deliveries: Mapped[List["CampaignDelivery"]] = relationship(
        "CampaignDelivery",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[List["CampaignAttachment"]] = relationship(
        "CampaignAttachment",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignAttachment.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} company_id={self.company_id} name='{self.name}' status='{self.status}'>"


class CampaignRecipient(Base):
    """Recipient attached to a campaign for personalized delivery and tracking."""
    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    custom_variables: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)

    status: Mapped[str] = mapped_column(
        String(50),
        default=CampaignRecipientStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_campaign_recipient_email"),
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")
    deliveries: Mapped[List["CampaignDelivery"]] = relationship(
        "CampaignDelivery",
        back_populates="recipient",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<CampaignRecipient id={self.id} campaign_id={self.campaign_id} email='{self.email}' status='{self.status}'>"


class CampaignDelivery(Base):
    """Individual dispatch record linking a campaign recipient to an outgoing email message.
    
    Maintains delivery state, retry attempts, bounce timestamps, and links
    to the underlying Email record and recipient-specific EmailThread.
    """
    __tablename__ = "campaign_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaign_recipients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("emails.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("email_threads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(50),
        default=CampaignDeliveryStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "recipient_id", name="uq_campaign_delivery_recipient"),
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="deliveries")
    recipient: Mapped["CampaignRecipient"] = relationship("CampaignRecipient", back_populates="deliveries")
    email: Mapped[Optional["Email"]] = relationship("Email")
    thread: Mapped[Optional["EmailThread"]] = relationship("EmailThread")

    def __repr__(self) -> str:
        return f"<CampaignDelivery id={self.id} campaign_id={self.campaign_id} recipient_id={self.recipient_id} status='{self.status}'>"


class SuppressionEntry(Base):
    """Company-scoped suppression list preventing unwanted deliveries to bounced,
    unsubscribed, or manually suppressed recipients.
    """
    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(
        String(50),
        default=SuppressionReason.MANUAL.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_company_suppression_email"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")

    def __repr__(self) -> str:
        return f"<SuppressionEntry id={self.id} company_id={self.company_id} email='{self.email}' reason='{self.reason}'>"


class CampaignAttachment(Base):
    """Database representation of an email attachment associated with a campaign.

    Stores metadata including filename, MIME type, size, and secure storage path.
    Reuses the existing AttachmentStorageService filesystem location and MIME handling.
    """
    __tablename__ = "campaign_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("email_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="attachments")
    company: Mapped["Company"] = relationship("Company")
    email_account: Mapped["EmailAccount"] = relationship("EmailAccount")

    def __repr__(self) -> str:
        return f"<CampaignAttachment id={self.id} file_name='{self.file_name}' size={self.file_size} campaign_id={self.campaign_id}>"
