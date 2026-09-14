"""Add imap_uid to emails and last_synced_at to email_accounts

Revision ID: 005_add_imap_fields
Revises: 004_create_emails
Create Date: 2026-09-14 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005_add_imap_fields"
down_revision: Union[str, None] = "004_create_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add imap_uid column and indexes to emails
    op.add_column("emails", sa.Column("imap_uid", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_emails_imap_uid"), "emails", ["imap_uid"], unique=False)
    op.create_index("ix_emails_account_uid", "emails", ["email_account_id", "imap_uid"], unique=True)
    op.create_index("ix_emails_account_message_id", "emails", ["email_account_id", "message_id"], unique=False)

    # 2. Add last_synced_at column to email_accounts
    op.add_column("email_accounts", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # 1. Remove last_synced_at from email_accounts
    op.drop_column("email_accounts", "last_synced_at")

    # 2. Drop indexes and imap_uid from emails
    op.drop_index("ix_emails_account_message_id", table_name="emails")
    op.drop_index("ix_emails_account_uid", table_name="emails")
    op.drop_index(op.f("ix_emails_imap_uid"), table_name="emails")
    op.drop_column("emails", "imap_uid")
