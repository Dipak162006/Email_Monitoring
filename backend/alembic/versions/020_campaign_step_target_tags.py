"""Add target_tags to campaign_steps table

Revision ID: 020_campaign_step_target_tags
Revises: 019_add_source_attachment_id
Create Date: 2026-10-28 14:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "020_campaign_step_target_tags"
down_revision: Union[str, None] = "019_add_source_attachment_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add target_tags JSON column to campaign_steps
    op.add_column(
        "campaign_steps",
        sa.Column("target_tags", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_steps", "target_tags")

