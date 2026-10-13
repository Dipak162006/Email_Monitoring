"""Add campaign send_interval_seconds and next_send_at

Revision ID: 017_add_campaign_send_interval_and_next_send_at
Revises: 016_create_campaign_attachments
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "017_campaign_send_interval"
down_revision: Union[str, None] = "016_create_campaign_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "send_interval_seconds",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "next_send_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_campaigns_next_send_at", "campaigns", ["next_send_at"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_next_send_at", table_name="campaigns")
    op.drop_column("campaigns", "next_send_at")
    op.drop_column("campaigns", "send_interval_seconds")
