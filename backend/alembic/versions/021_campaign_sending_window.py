"""Add sending_window to campaigns table

Revision ID: 021_campaign_sending_window
Revises: 020_campaign_step_target_tags
Create Date: 2026-10-28 15:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "021_campaign_sending_window"
down_revision: Union[str, None] = "020_campaign_step_target_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sending_window nullable JSON column to campaigns table
    op.add_column(
        "campaigns",
        sa.Column(
            "sending_window",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "sending_window")

