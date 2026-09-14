"""Add email mailbox fields: is_deleted, deleted_at and index

Revision ID: 007_add_email_mailbox_fields
Revises: 006_create_email_threads
Create Date: 2026-09-14 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007_add_email_mailbox_fields"
down_revision: Union[str, None] = "006_create_email_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emails",
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "emails",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_emails_is_deleted"), "emails", ["is_deleted"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emails_is_deleted"), table_name="emails")
    op.drop_column("emails", "deleted_at")
    op.drop_column("emails", "is_deleted")
