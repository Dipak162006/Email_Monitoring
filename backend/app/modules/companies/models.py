from datetime import datetime
import enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.email_accounts.models import EmailAccount
    from app.modules.emails.models import Email, EmailThread


class CompanyRole(str, enum.Enum):
    """Roles for users within a company."""
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class InvitationStatus(str, enum.Enum):
    """Lifecycle statuses for company invitations."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"


class Company(Base):
    """Company database model representing a tenant organization.
    
    A company owns company email accounts (M4) and has multiple users
    with specific roles via CompanyUser memberships.
    """
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    members: Mapped[List["CompanyUser"]] = relationship(
        "CompanyUser",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    email_accounts: Mapped[List["EmailAccount"]] = relationship(
        "EmailAccount",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    emails: Mapped[List["Email"]] = relationship(
        "Email",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    threads: Mapped[List["EmailThread"]] = relationship(
        "EmailThread",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[List["CompanyInvitation"]] = relationship(
        "CompanyInvitation",
        back_populates="company",
        cascade="all, delete-orphan",
    )


    def __repr__(self) -> str:
        return f"<Company id={self.id} name='{self.name}' active={self.is_active}>"


class CompanyUser(Base):
    """Relationship model connecting a User to a Company with an assigned role.
    
    Ensures that login users are decoupled from email accounts and isolated
    at the company tenant level.
    """
    __tablename__ = "company_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default=CompanyRole.MEMBER.value,
        nullable=False,
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

    # Constraints
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_user"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="company_memberships")

    def __repr__(self) -> str:
        return f"<CompanyUser company_id={self.company_id} user_id={self.user_id} role='{self.role}'>"


class CompanyInvitation(Base):
    """Invitation to join a company workspace with an assigned role.
    
    Created by an authorized company owner/admin.
    Accepted or declined by the invited user.
    """
    __tablename__ = "company_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    invited_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    inviter_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default=CompanyRole.MEMBER.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=InvitationStatus.PENDING.value,
        nullable=False,
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
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    declined_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="invitations")
    inviter: Mapped["User"] = relationship("User", foreign_keys=[inviter_user_id])
    invited_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[invited_user_id])

    def __repr__(self) -> str:
        return f"<CompanyInvitation id={self.id} company_id={self.company_id} email='{self.invited_email}' role='{self.role}' status='{self.status}'>"

