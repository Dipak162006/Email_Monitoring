from datetime import datetime
import enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.companies.models import Company
    from app.modules.email_accounts.models import EmailAccount


class DomainVerificationStatus(str, enum.Enum):
    """Lifecycle statuses for domain DNS verification."""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class Domain(Base):
    """Domain database model representing an organization's sending domain.
    
    A domain strictly belongs to a Company organization tenant.
    Tracks DNS records verification statuses (SPF, DKIM, DMARC, MX).
    """
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(
        String(50),
        default=DomainVerificationStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    spf_status: Mapped[str] = mapped_column(
        String(50),
        default=DomainVerificationStatus.PENDING.value,
        nullable=False,
    )
    dkim_status: Mapped[str] = mapped_column(
        String(50),
        default=DomainVerificationStatus.PENDING.value,
        nullable=False,
    )
    dmarc_status: Mapped[str] = mapped_column(
        String(50),
        default=DomainVerificationStatus.PENDING.value,
        nullable=False,
    )
    mx_status: Mapped[str] = mapped_column(
        String(50),
        default=DomainVerificationStatus.PENDING.value,
        nullable=False,
    )
    dkim_selector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
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
        UniqueConstraint("company_id", "domain_name", name="uq_company_domain_name"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="domains")
    email_accounts: Mapped[List["EmailAccount"]] = relationship("EmailAccount", back_populates="domain")

    def __repr__(self) -> str:
        return f"<Domain id={self.id} company_id={self.company_id} name='{self.domain_name}' status='{self.verification_status}'>"
