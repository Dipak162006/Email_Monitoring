"""Create email attachments table

Revision ID: 011_create_email_attachments
Revises: 010_unique_default_signature
Create Date: 2026-09-16 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011_create_email_attachments"
down_revision: Union[str, None] = "010_unique_default_signature"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
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
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_attachments_id", "email_attachments", ["id"])
    op.create_index("ix_email_attachments_company_id", "email_attachments", ["company_id"])
    op.create_index("ix_email_attachments_email_account_id", "email_attachments", ["email_account_id"])
    op.create_index("ix_email_attachments_email_id", "email_attachments", ["email_id"])


def downgrade() -> None:
    op.drop_index("ix_email_attachments_email_id", table_name="email_attachments")
    op.drop_index("ix_email_attachments_email_account_id", table_name="email_attachments")
    op.drop_index("ix_email_attachments_company_id", table_name="email_attachments")
    op.drop_index("ix_email_attachments_id", table_name="email_attachments")
    op.drop_table("email_attachments")
