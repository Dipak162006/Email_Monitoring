"""Create emails table

Revision ID: 004_create_emails
Revises: 003_create_email_accounts
Create Date: 2026-09-14 15:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_create_emails"
down_revision: Union[str, None] = "003_create_email_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("in_reply_to", sa.String(length=255), nullable=True),
        sa.Column("references_header", sa.Text(), nullable=True),
        sa.Column("direction", sa.String(length=50), server_default=sa.text("'OUTGOING'"), nullable=False),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'SENT'"), nullable=False),
        sa.Column("sender", sa.String(length=255), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("cc", sa.JSON(), nullable=True),
        sa.Column("bcc", sa.JSON(), nullable=True),
        sa.Column("reply_to", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=998), server_default=sa.text("''"), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_starred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_emails_id"), "emails", ["id"], unique=False)
    op.create_index(op.f("ix_emails_company_id"), "emails", ["company_id"], unique=False)
    op.create_index(op.f("ix_emails_email_account_id"), "emails", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_emails_user_id"), "emails", ["user_id"], unique=False)
    op.create_index(op.f("ix_emails_message_id"), "emails", ["message_id"], unique=False)
    op.create_index(op.f("ix_emails_direction"), "emails", ["direction"], unique=False)
    op.create_index(op.f("ix_emails_status"), "emails", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emails_status"), table_name="emails")
    op.drop_index(op.f("ix_emails_direction"), table_name="emails")
    op.drop_index(op.f("ix_emails_message_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_user_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_email_account_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_company_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_id"), table_name="emails")
    op.drop_table("emails")
