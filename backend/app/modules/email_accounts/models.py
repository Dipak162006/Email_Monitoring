from datetime import datetime
import enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.companies.models import Company
    from app.modules.emails.models import Email, EmailThread


class EmailProvider(str, enum.Enum):
    """Supported email service providers."""
    GOOGLE = "GOOGLE"
    YAHOO = "YAHOO"
    ZOHO = "ZOHO"
    CUSTOM = "CUSTOM"


class SecurityMode(str, enum.Enum):
    """Transport layer security / encryption modes for SMTP and IMAP."""
    NONE = "NONE"
    SSL = "SSL"
    STARTTLS = "STARTTLS"


class EmailAccount(Base):
    """Company-owned email account configuration for sending (SMTP) and receiving (IMAP).
    
    Email accounts are strictly company-owned and decoupled from application login identities.
    Sensitive credentials are encrypted at rest using AES-authenticated encryption.
    """
    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(50),
        default=EmailProvider.CUSTOM.value,
        nullable=False,
    )

    # SMTP Configuration (Outgoing)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    smtp_security: Mapped[Optional[str]] = mapped_column(
        String(50),
        default=SecurityMode.STARTTLS.value,
        nullable=True,
    )
    smtp_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_password_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # IMAP Configuration (Incoming)
    imap_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    imap_security: Mapped[Optional[str]] = mapped_column(
        String(50),
        default=SecurityMode.SSL.value,
        nullable=True,
    )
    imap_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    imap_password_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
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
    company: Mapped["Company"] = relationship("Company", back_populates="email_accounts")
    user_access: Mapped[List["EmailAccountAccess"]] = relationship(
        "EmailAccountAccess",
        back_populates="email_account",
        cascade="all, delete-orphan",
    )
    emails: Mapped[List["Email"]] = relationship(
        "Email",
        back_populates="email_account",
        cascade="all, delete-orphan",
    )
    threads: Mapped[List["EmailThread"]] = relationship(
        "EmailThread",
        back_populates="email_account",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<EmailAccount id={self.id} address='{self.email_address}' company_id={self.company_id}>"


class EmailAccountAccess(Base):
    """Authorization model controlling which company users can use an email account.
    
    A user may only be granted access to an email account belonging to a company
    they are an active member of.
    """
    __tablename__ = "email_account_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    email_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("email_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("email_account_id", "user_id", name="uq_email_account_user"),
    )

    # Relationships
    email_account: Mapped["EmailAccount"] = relationship("EmailAccount", back_populates="user_access")
    user: Mapped["User"] = relationship("User", back_populates="email_account_access")

    def __repr__(self) -> str:
        return f"<EmailAccountAccess email_account_id={self.email_account_id} user_id={self.user_id}>"
