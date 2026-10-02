"""Create company invitations table

Revision ID: 012_create_company_invitations
Revises: 011_create_email_attachments
Create Date: 2026-10-01 13:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012_create_company_invitations"
down_revision: Union[str, None] = "011_create_email_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_invitations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column("invited_user_id", sa.Integer(), nullable=True),
        sa.Column("inviter_user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), server_default=sa.text("'MEMBER'"), nullable=False),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
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
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_invitations_id"), "company_invitations", ["id"], unique=False)
    op.create_index(op.f("ix_company_invitations_company_id"), "company_invitations", ["company_id"], unique=False)
    op.create_index(op.f("ix_company_invitations_invited_email"), "company_invitations", ["invited_email"], unique=False)
    op.create_index(op.f("ix_company_invitations_invited_user_id"), "company_invitations", ["invited_user_id"], unique=False)
    op.create_index(op.f("ix_company_invitations_inviter_user_id"), "company_invitations", ["inviter_user_id"], unique=False)
    op.create_index(op.f("ix_company_invitations_status"), "company_invitations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_company_invitations_status"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_inviter_user_id"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_invited_user_id"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_invited_email"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_company_id"), table_name="company_invitations")
    op.drop_index(op.f("ix_company_invitations_id"), table_name="company_invitations")
    op.drop_table("company_invitations")
