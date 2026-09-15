"""Create email_templates table

Revision ID: 008_create_email_templates
Revises: 007_add_email_mailbox_fields
Create Date: 2026-09-15 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_create_email_templates"
down_revision: Union[str, None] = "007_add_email_mailbox_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=998), server_default=sa.text("''"), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_templates_id"), "email_templates", ["id"], unique=False)
    op.create_index(op.f("ix_email_templates_company_id"), "email_templates", ["company_id"], unique=False)
    op.create_index(op.f("ix_email_templates_email_account_id"), "email_templates", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_email_templates_user_id"), "email_templates", ["user_id"], unique=False)
    op.create_index(op.f("ix_email_templates_name"), "email_templates", ["name"], unique=False)
    op.create_index(op.f("ix_email_templates_is_active"), "email_templates", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_templates_is_active"), table_name="email_templates")
    op.drop_index(op.f("ix_email_templates_name"), table_name="email_templates")
    op.drop_index(op.f("ix_email_templates_user_id"), table_name="email_templates")
    op.drop_index(op.f("ix_email_templates_email_account_id"), table_name="email_templates")
    op.drop_index(op.f("ix_email_templates_company_id"), table_name="email_templates")
    op.drop_index(op.f("ix_email_templates_id"), table_name="email_templates")
    op.drop_table("email_templates")
