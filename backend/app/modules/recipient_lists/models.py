from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
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


class RecipientList(Base):
    """Reusable recipient list owned by a company tenant."""
    __tablename__ = "recipient_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_recipient_list_company_name"),
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company")
    creator: Mapped[Optional["User"]] = relationship("User")
    members: Mapped[List["RecipientListMember"]] = relationship(
        "RecipientListMember",
        back_populates="recipient_list",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<RecipientList id={self.id} company_id={self.company_id} name={self.name!r}>"


class RecipientListMember(Base):
    """A contact belonging to a reusable RecipientList."""
    __tablename__ = "recipient_list_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recipient_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

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

    __table_args__ = (
        UniqueConstraint("list_id", "email", name="uq_recipient_list_member_list_email"),
    )

    # Relationships
    recipient_list: Mapped["RecipientList"] = relationship(
        "RecipientList",
        back_populates="members",
    )

    def __repr__(self) -> str:
        return f"<RecipientListMember id={self.id} list_id={self.list_id} email={self.email!r}>"
