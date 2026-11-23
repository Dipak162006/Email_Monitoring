"""Add remote_event_id BigInteger unique constraint and make token_id nullable on email_tracking_events

Revision ID: 027_tracking_events_remote_id
Revises: 026_events_nullable_bot
Create Date: 2026-11-20 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = "027_tracking_events_remote_id"
down_revision: Union[str, None] = "026_events_nullable_bot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c["name"] for c in inspector.get_columns("email_tracking_events")]
    indexes = [idx["name"] for idx in inspector.get_indexes("email_tracking_events")]
    fks = inspector.get_foreign_keys("email_tracking_events")

    # 1. Add remote_event_id column using BigInteger if not exists, or alter type to BigInteger
    if "remote_event_id" not in columns:
        op.add_column(
            "email_tracking_events",
            sa.Column("remote_event_id", sa.BigInteger(), nullable=True),
        )
    else:
        op.alter_column(
            "email_tracking_events",
            "remote_event_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            nullable=True,
        )

    # 2. Add unique index on remote_event_id
    if "ix_email_tracking_events_remote_event_id" not in indexes:
        op.create_index(
            "ix_email_tracking_events_remote_event_id",
            "email_tracking_events",
            ["remote_event_id"],
            unique=True,
        )

    # 3. Make token_id nullable
    op.alter_column(
        "email_tracking_events",
        "token_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 4. Safely drop token foreign key if exists
    for fk in fks:
        if fk.get("name") == "email_tracking_events_token_id_fkey" or (
            "token_id" in fk.get("constrained_columns", [])
        ):
            op.drop_constraint(fk["name"], "email_tracking_events", type_="foreignkey")

    # 5. Make email_id nullable so delivery-level tracking events do not fail when email_id is unassigned
    op.alter_column(
        "email_tracking_events",
        "email_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Safety Check: Never delete synchronized events; check for incompatible NULL values
    null_count = conn.execute(
        sa.text(
            "SELECT count(*) FROM email_tracking_events WHERE token_id IS NULL OR email_id IS NULL"
        )
    ).scalar() or 0

    if null_count > 0:
        raise RuntimeError(
            f"Cannot safely downgrade migration 027: email_tracking_events contains {null_count} "
            "row(s) with NULL token_id or email_id from synchronized remote interaction events. "
            "Re-applying NOT NULL would fail and dropping remote_event_id would permanently lose "
            "remote synchronization identity. Downgrade refused to protect data integrity."
        )

    inspector = Inspector.from_engine(conn)
    indexes = [idx["name"] for idx in inspector.get_indexes("email_tracking_events")]

    if "ix_email_tracking_events_remote_event_id" in indexes:
        op.drop_index("ix_email_tracking_events_remote_event_id", table_name="email_tracking_events")
    
    op.drop_column("email_tracking_events", "remote_event_id")
    op.alter_column("email_tracking_events", "token_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("email_tracking_events", "email_id", existing_type=sa.Integer(), nullable=False)
