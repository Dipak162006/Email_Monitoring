"""Create email_accounts and email_account_access tables

Revision ID: 003_create_email_accounts
Revises: 002_create_companies
Create Date: 2026-09-14 14:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_create_email_accounts"
down_revision: Union[str, None] = "002_create_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create email_accounts table
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=50), server_default=sa.text("'CUSTOM'"), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_security", sa.String(length=50), server_default=sa.text("'STARTTLS'"), nullable=True),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("smtp_password_encrypted", sa.String(length=512), nullable=True),
        sa.Column("imap_host", sa.String(length=255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=True),
        sa.Column("imap_security", sa.String(length=50), server_default=sa.text("'SSL'"), nullable=True),
        sa.Column("imap_username", sa.String(length=255), nullable=True),
        sa.Column("imap_password_encrypted", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_accounts_id"), "email_accounts", ["id"], unique=False)
    op.create_index(op.f("ix_email_accounts_company_id"), "email_accounts", ["company_id"], unique=False)
    op.create_index(op.f("ix_email_accounts_email_address"), "email_accounts", ["email_address"], unique=False)

    # 2. Create email_account_access table
    op.create_table(
        "email_account_access",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_account_id", "user_id", name="uq_email_account_user"),
    )
    op.create_index(op.f("ix_email_account_access_id"), "email_account_access", ["id"], unique=False)
    op.create_index(op.f("ix_email_account_access_email_account_id"), "email_account_access", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_email_account_access_user_id"), "email_account_access", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_account_access_user_id"), table_name="email_account_access")
    op.drop_index(op.f("ix_email_account_access_email_account_id"), table_name="email_account_access")
    op.drop_index(op.f("ix_email_account_access_id"), table_name="email_account_access")
    op.drop_table("email_account_access")
    op.drop_index(op.f("ix_email_accounts_email_address"), table_name="email_accounts")
    op.drop_index(op.f("ix_email_accounts_company_id"), table_name="email_accounts")
    op.drop_index(op.f("ix_email_accounts_id"), table_name="email_accounts")
    op.drop_table("email_accounts")
