"""Create campaigns tables

Revision ID: 015_create_campaigns_tables
Revises: 014_email_accounts_domain_id
Create Date: 2026-10-07 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "015_create_campaigns_tables"
down_revision: Union[str, None] = "014_email_accounts_domain_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create campaigns table
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=998), server_default=sa.text("''"), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaigns_id"), "campaigns", ["id"], unique=False)
    op.create_index(op.f("ix_campaigns_company_id"), "campaigns", ["company_id"], unique=False)
    op.create_index(op.f("ix_campaigns_email_account_id"), "campaigns", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_campaigns_name"), "campaigns", ["name"], unique=False)
    op.create_index(op.f("ix_campaigns_status"), "campaigns", ["status"], unique=False)
    op.create_index(op.f("ix_campaigns_scheduled_at"), "campaigns", ["scheduled_at"], unique=False)
    op.create_index(op.f("ix_campaigns_created_by_user_id"), "campaigns", ["created_by_user_id"], unique=False)

    # 2. Create campaign_recipients table
    op.create_table(
        "campaign_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("custom_variables", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "email", name="uq_campaign_recipient_email"),
    )
    op.create_index(op.f("ix_campaign_recipients_id"), "campaign_recipients", ["id"], unique=False)
    op.create_index(op.f("ix_campaign_recipients_campaign_id"), "campaign_recipients", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_campaign_recipients_email"), "campaign_recipients", ["email"], unique=False)
    op.create_index(op.f("ix_campaign_recipients_status"), "campaign_recipients", ["status"], unique=False)

    # 3. Create campaign_deliveries table
    op.create_table(
        "campaign_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("email_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["campaign_recipients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_id"], ["emails.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["email_threads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "recipient_id", name="uq_campaign_delivery_recipient"),
    )
    op.create_index(op.f("ix_campaign_deliveries_id"), "campaign_deliveries", ["id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_campaign_id"), "campaign_deliveries", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_recipient_id"), "campaign_deliveries", ["recipient_id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_email_id"), "campaign_deliveries", ["email_id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_thread_id"), "campaign_deliveries", ["thread_id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_message_id"), "campaign_deliveries", ["message_id"], unique=False)
    op.create_index(op.f("ix_campaign_deliveries_status"), "campaign_deliveries", ["status"], unique=False)

    # 4. Create suppression_list table
    op.create_table(
        "suppression_list",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=50), server_default=sa.text("'MANUAL'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "email", name="uq_company_suppression_email"),
    )
    op.create_index(op.f("ix_suppression_list_id"), "suppression_list", ["id"], unique=False)
    op.create_index(op.f("ix_suppression_list_company_id"), "suppression_list", ["company_id"], unique=False)
    op.create_index(op.f("ix_suppression_list_email"), "suppression_list", ["email"], unique=False)
    op.create_index(op.f("ix_suppression_list_reason"), "suppression_list", ["reason"], unique=False)


def downgrade() -> None:
    # Drop suppression_list
    op.drop_index(op.f("ix_suppression_list_reason"), table_name="suppression_list")
    op.drop_index(op.f("ix_suppression_list_email"), table_name="suppression_list")
    op.drop_index(op.f("ix_suppression_list_company_id"), table_name="suppression_list")
    op.drop_index(op.f("ix_suppression_list_id"), table_name="suppression_list")
    op.drop_table("suppression_list")

    # Drop campaign_deliveries
    op.drop_index(op.f("ix_campaign_deliveries_status"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_message_id"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_thread_id"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_email_id"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_recipient_id"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_campaign_id"), table_name="campaign_deliveries")
    op.drop_index(op.f("ix_campaign_deliveries_id"), table_name="campaign_deliveries")
    op.drop_table("campaign_deliveries")

    # Drop campaign_recipients
    op.drop_index(op.f("ix_campaign_recipients_status"), table_name="campaign_recipients")
    op.drop_index(op.f("ix_campaign_recipients_email"), table_name="campaign_recipients")
    op.drop_index(op.f("ix_campaign_recipients_campaign_id"), table_name="campaign_recipients")
    op.drop_index(op.f("ix_campaign_recipients_id"), table_name="campaign_recipients")
    op.drop_table("campaign_recipients")

    # Drop campaigns
    op.drop_index(op.f("ix_campaigns_created_by_user_id"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_scheduled_at"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_status"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_name"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_email_account_id"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_company_id"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_id"), table_name="campaigns")
    op.drop_table("campaigns")
