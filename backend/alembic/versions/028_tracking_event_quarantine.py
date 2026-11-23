"""Create tracking_event_quarantine table for durable event rejection audit

Revision ID: 028_tracking_event_quarantine
Revises: 027_tracking_events_remote_id
Create Date: 2026-11-20 14:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = "028_tracking_event_quarantine"
down_revision: Union[str, None] = "027_tracking_events_remote_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "tracking_event_quarantine" not in tables:
        op.create_table(
            "tracking_event_quarantine",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("remote_event_id", sa.BigInteger(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("replay_status", sa.String(length=50), server_default=sa.text("'pending'"), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tracking_event_quarantine_id", "tracking_event_quarantine", ["id"])
        op.create_index(
            "ix_tracking_event_quarantine_remote_event_id",
            "tracking_event_quarantine",
            ["remote_event_id"],
            unique=True,
        )
        op.create_index("ix_tracking_event_quarantine_company_id", "tracking_event_quarantine", ["company_id"])
        op.create_index("ix_tracking_event_quarantine_replay_status", "tracking_event_quarantine", ["replay_status"])


def downgrade() -> None:
    op.drop_table("tracking_event_quarantine")
