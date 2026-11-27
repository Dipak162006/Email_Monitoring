"""Create recipient_lists and recipient_list_members tables

Revision ID: 029_create_recipient_lists
Revises: 028_tracking_event_quarantine
Create Date: 2026-11-27 10:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = "029_create_recipient_lists"
down_revision: Union[str, None] = "028_tracking_event_quarantine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "recipient_lists" not in tables:
        op.create_table(
            "recipient_lists",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "name", name="uq_recipient_list_company_name"),
        )
        op.create_index(op.f("ix_recipient_lists_id"), "recipient_lists", ["id"], unique=False)
        op.create_index(op.f("ix_recipient_lists_company_id"), "recipient_lists", ["company_id"], unique=False)
        op.create_index(op.f("ix_recipient_lists_name"), "recipient_lists", ["name"], unique=False)
        op.create_index(op.f("ix_recipient_lists_created_by_user_id"), "recipient_lists", ["created_by_user_id"], unique=False)

    if "recipient_list_members" not in tables:
        op.create_table(
            "recipient_list_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("list_id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("first_name", sa.String(length=100), nullable=True),
            sa.Column("last_name", sa.String(length=100), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["list_id"], ["recipient_lists.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("list_id", "email", name="uq_recipient_list_member_list_email"),
        )
        op.create_index(op.f("ix_recipient_list_members_id"), "recipient_list_members", ["id"], unique=False)
        op.create_index(op.f("ix_recipient_list_members_list_id"), "recipient_list_members", ["list_id"], unique=False)
        op.create_index(op.f("ix_recipient_list_members_email"), "recipient_list_members", ["email"], unique=False)


def downgrade() -> None:
    op.drop_table("recipient_list_members")
    op.drop_table("recipient_lists")
