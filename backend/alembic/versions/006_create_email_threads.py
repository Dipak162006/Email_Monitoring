"""Create email_threads table and add thread_id to emails

Revision ID: 006_create_email_threads
Revises: 005_add_imap_fields
Create Date: 2026-09-14 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006_create_email_threads"
down_revision: Union[str, None] = "005_add_imap_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create email_threads table
    op.create_table(
        "email_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=998), server_default=sa.text("''"), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("has_reply", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_threads_id"), "email_threads", ["id"], unique=False)
    op.create_index(op.f("ix_email_threads_company_id"), "email_threads", ["company_id"], unique=False)
    op.create_index(op.f("ix_email_threads_email_account_id"), "email_threads", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_email_threads_last_message_at"), "email_threads", ["last_message_at"], unique=False)

    # 2. Add thread_id to emails table
    op.add_column("emails", sa.Column("thread_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_emails_thread_id_email_threads",
        "emails",
        "email_threads",
        ["thread_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_emails_thread_id"), "emails", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emails_thread_id"), table_name="emails")
    op.drop_constraint("fk_emails_thread_id_email_threads", "emails", type_="foreignkey")
    op.drop_column("emails", "thread_id")
    op.drop_index(op.f("ix_email_threads_last_message_at"), table_name="email_threads")
    op.drop_index(op.f("ix_email_threads_email_account_id"), table_name="email_threads")
    op.drop_index(op.f("ix_email_threads_company_id"), table_name="email_threads")
    op.drop_index(op.f("ix_email_threads_id"), table_name="email_threads")
    op.drop_table("email_threads")
