"""Decouple tracking foreign keys and add idempotency key

Revision ID: 025_decouple_tracking_fkeys
Revises: 024_email_tracking_tables
Create Date: 2026-11-05 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "025_decouple_tracking_fkeys"
down_revision: Union[str, None] = "024_email_tracking_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop foreign key constraints on email_tracking_tokens
    op.drop_constraint("email_tracking_tokens_company_id_fkey", "email_tracking_tokens", type_="foreignkey")
    op.drop_constraint("email_tracking_tokens_email_id_fkey", "email_tracking_tokens", type_="foreignkey")
    op.drop_constraint("email_tracking_tokens_campaign_id_fkey", "email_tracking_tokens", type_="foreignkey")
    op.drop_constraint("email_tracking_tokens_recipient_id_fkey", "email_tracking_tokens", type_="foreignkey")
    op.drop_constraint("email_tracking_tokens_delivery_id_fkey", "email_tracking_tokens", type_="foreignkey")

    # 2. Drop foreign key constraints on email_tracking_events (except token_id which is internal)
    op.drop_constraint("email_tracking_events_company_id_fkey", "email_tracking_events", type_="foreignkey")
    op.drop_constraint("email_tracking_events_email_id_fkey", "email_tracking_events", type_="foreignkey")
    op.drop_constraint("email_tracking_events_campaign_id_fkey", "email_tracking_events", type_="foreignkey")
    op.drop_constraint("email_tracking_events_recipient_id_fkey", "email_tracking_events", type_="foreignkey")
    op.drop_constraint("email_tracking_events_delivery_id_fkey", "email_tracking_events", type_="foreignkey")

    # 3. Add idempotency_key column and index to email_tracking_tokens
    op.add_column("email_tracking_tokens", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_email_tracking_tokens_idempotency_key",
        "email_tracking_tokens",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    # 1. Remove idempotency_key index and column
    op.drop_index("ix_email_tracking_tokens_idempotency_key", table_name="email_tracking_tokens", if_exists=True)
    op.drop_column("email_tracking_tokens", "idempotency_key")

    # 2. Re-create foreign key constraints on email_tracking_events
    op.create_foreign_key(
        "email_tracking_events_delivery_id_fkey",
        "email_tracking_events",
        "campaign_deliveries",
        ["delivery_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_events_recipient_id_fkey",
        "email_tracking_events",
        "campaign_recipients",
        ["recipient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_events_campaign_id_fkey",
        "email_tracking_events",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_events_email_id_fkey",
        "email_tracking_events",
        "emails",
        ["email_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_events_company_id_fkey",
        "email_tracking_events",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3. Re-create foreign key constraints on email_tracking_tokens
    op.create_foreign_key(
        "email_tracking_tokens_delivery_id_fkey",
        "email_tracking_tokens",
        "campaign_deliveries",
        ["delivery_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_tokens_recipient_id_fkey",
        "email_tracking_tokens",
        "campaign_recipients",
        ["recipient_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_tokens_campaign_id_fkey",
        "email_tracking_tokens",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_tokens_email_id_fkey",
        "email_tracking_tokens",
        "emails",
        ["email_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_tracking_tokens_company_id_fkey",
        "email_tracking_tokens",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )

