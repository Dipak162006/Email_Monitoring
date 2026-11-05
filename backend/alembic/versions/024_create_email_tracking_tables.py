"""Create email tracking tokens and email tracking events tables

Revision ID: 024_email_tracking_tables
Revises: 023_email_attachment_disposition
Create Date: 2026-11-05 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "024_email_tracking_tables"
down_revision: Union[str, None] = "023_email_attachment_disposition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create email_tracking_tokens table
    op.create_table(
        "email_tracking_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("recipient_id", sa.Integer(), nullable=True),
        sa.Column("delivery_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delivery_id"], ["campaign_deliveries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["campaign_recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_email_tracking_tokens_token_hash"),
    )

    op.create_index("ix_email_tracking_tokens_id", "email_tracking_tokens", ["id"])
    op.create_index("ix_email_tracking_tokens_company_id", "email_tracking_tokens", ["company_id"])
    op.create_index("ix_email_tracking_tokens_email_id", "email_tracking_tokens", ["email_id"])
    op.create_index("ix_email_tracking_tokens_campaign_id", "email_tracking_tokens", ["campaign_id"])
    op.create_index("ix_email_tracking_tokens_recipient_id", "email_tracking_tokens", ["recipient_id"])
    op.create_index("ix_email_tracking_tokens_delivery_id", "email_tracking_tokens", ["delivery_id"])
    op.create_index("ix_email_tracking_tokens_token_hash", "email_tracking_tokens", ["token_hash"], unique=True)
    op.create_index("ix_email_tracking_tokens_token_type", "email_tracking_tokens", ["token_type"])
    op.create_index("ix_email_tracking_tokens_expires_at", "email_tracking_tokens", ["expires_at"])
    op.create_index(
        "ix_email_tracking_tokens_lookup",
        "email_tracking_tokens",
        ["token_hash", "token_type", "is_revoked"],
    )

    # 2. Create email_tracking_events table
    op.create_table(
        "email_tracking_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("recipient_id", sa.Integer(), nullable=True),
        sa.Column("delivery_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("bot_reason", sa.String(length=100), nullable=True),
        sa.Column("bot_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delivery_id"], ["campaign_deliveries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["campaign_recipients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["token_id"], ["email_tracking_tokens.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_email_tracking_events_id", "email_tracking_events", ["id"])
    op.create_index("ix_email_tracking_events_company_id", "email_tracking_events", ["company_id"])
    op.create_index("ix_email_tracking_events_token_id", "email_tracking_events", ["token_id"])
    op.create_index("ix_email_tracking_events_email_id", "email_tracking_events", ["email_id"])
    op.create_index("ix_email_tracking_events_campaign_id", "email_tracking_events", ["campaign_id"])
    op.create_index("ix_email_tracking_events_recipient_id", "email_tracking_events", ["recipient_id"])
    op.create_index("ix_email_tracking_events_delivery_id", "email_tracking_events", ["delivery_id"])
    op.create_index("ix_email_tracking_events_event_type", "email_tracking_events", ["event_type"])
    op.create_index("ix_email_tracking_events_occurred_at", "email_tracking_events", ["occurred_at"])
    op.create_index(
        "ix_email_tracking_events_company_type_time",
        "email_tracking_events",
        ["company_id", "event_type", "occurred_at"],
    )
    op.create_index(
        "ix_email_tracking_events_campaign_type",
        "email_tracking_events",
        ["campaign_id", "event_type"],
    )


def downgrade() -> None:
    # Drop tables in reverse order to respect foreign key constraints
    op.drop_table("email_tracking_events")
    op.drop_table("email_tracking_tokens")

