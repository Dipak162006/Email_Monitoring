"""Create campaign attachments table

Revision ID: 016_create_campaign_attachments
Revises: 015_create_campaigns_tables
Create Date: 2026-10-12 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "016_create_campaign_attachments"
down_revision: Union[str, None] = "015_create_campaigns_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaign_attachments_id", "campaign_attachments", ["id"])
    op.create_index("ix_campaign_attachments_campaign_id", "campaign_attachments", ["campaign_id"])
    op.create_index("ix_campaign_attachments_company_id", "campaign_attachments", ["company_id"])
    op.create_index("ix_campaign_attachments_email_account_id", "campaign_attachments", ["email_account_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_attachments_email_account_id", table_name="campaign_attachments")
    op.drop_index("ix_campaign_attachments_company_id", table_name="campaign_attachments")
    op.drop_index("ix_campaign_attachments_campaign_id", table_name="campaign_attachments")
    op.drop_index("ix_campaign_attachments_id", table_name="campaign_attachments")
    op.drop_table("campaign_attachments")
