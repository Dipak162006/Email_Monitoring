from datetime import datetime
import enum
from typing import TYPE_CHECKING, Any, List, Optional
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount


class EmailDirection(str, enum.Enum):
    """Direction of an email message."""
    OUTGOING = "OUTGOING"
    INCOMING = "INCOMING"


class EmailStatus(str, enum.Enum):
    """Lifecycle status of an email message."""
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    RECEIVED = "RECEIVED"


class Email(Base):
    """Database representation of an email message (outgoing or incoming).
    
    Persists email metadata, headers, direction, delivery status, bodies,
    and timestamps for auditability, threading, and mailbox tracking.
    """
    __tablename__ = "emails"
    __table_args__ = (
        Index("ix_emails_account_uid", "email_account_id", "imap_uid", unique=True),
        Index("ix_emails_account_message_id", "email_account_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
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
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Identifiers & Threading Headers
    thread_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("email_threads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    imap_uid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    in_reply_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    references_header: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification & Status
    direction: Mapped[str] = mapped_column(
        String(50),
        default=EmailDirection.OUTGOING.value,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=EmailStatus.SENT.value,
        nullable=False,
        index=True,
    )

    # Message Addressing
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    recipients: Mapped[List[Any]] = mapped_column(JSON, nullable=False)
    cc: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    bcc: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    reply_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Message Content
    subject: Mapped[str] = mapped_column(String(998), default="", nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Mailbox Flags
    is_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Delivery & Error Tracking
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    company: Mapped["Company"] = relationship("Company", back_populates="emails")
    email_account: Mapped["EmailAccount"] = relationship("EmailAccount", back_populates="emails")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="sent_emails")
    thread: Mapped[Optional["EmailThread"]] = relationship("EmailThread", back_populates="emails")

    def __repr__(self) -> str:
        return f"<Email id={self.id} subject='{self.subject[:30]}' status={self.status} direction={self.direction}>"


class EmailThread(Base):
    """Database representation of a conversation thread grouping related emails.
    
    Maintains conversation metadata, participants, message count, latest activity timestamp,
    and reply tracking across outgoing and incoming emails.
    """
    __tablename__ = "email_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
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
    subject: Mapped[str] = mapped_column(String(998), default="", nullable=False)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    has_reply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
    company: Mapped["Company"] = relationship("Company", back_populates="threads")
    email_account: Mapped["EmailAccount"] = relationship("EmailAccount", back_populates="threads")
    emails: Mapped[List["Email"]] = relationship(
        "Email",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Email.sent_at.asc(), Email.created_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<EmailThread id={self.id} subject='{self.subject[:30]}' messages={self.message_count} has_reply={self.has_reply}>"

