"""Make email_tracking_events is_bot column nullable for unclassified raw events

Revision ID: 026_events_nullable_bot
Revises: 025_decouple_tracking_fkeys
Create Date: 2026-11-05 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "026_events_nullable_bot"
down_revision: Union[str, None] = "025_decouple_tracking_fkeys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow is_bot to be NULL so new raw tracking events are explicitly unclassified
    op.alter_column(
        "email_tracking_events",
        "is_bot",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # Backfill any unclassified NULL rows to false before re-adding NOT NULL constraint
    op.execute("UPDATE email_tracking_events SET is_bot = false WHERE is_bot IS NULL")
    op.alter_column(
        "email_tracking_events",
        "is_bot",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )

