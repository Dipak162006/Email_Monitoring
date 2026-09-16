"""Create email_signatures table

Revision ID: 009_create_email_signatures
Revises: 008_create_email_templates
Create Date: 2026-09-15 16:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009_create_email_signatures"
down_revision: Union[str, None] = "008_create_email_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_signatures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("email_account_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_signatures_id"), "email_signatures", ["id"], unique=False)
    op.create_index(op.f("ix_email_signatures_company_id"), "email_signatures", ["company_id"], unique=False)
    op.create_index(op.f("ix_email_signatures_email_account_id"), "email_signatures", ["email_account_id"], unique=False)
    op.create_index(op.f("ix_email_signatures_user_id"), "email_signatures", ["user_id"], unique=False)
    op.create_index(op.f("ix_email_signatures_name"), "email_signatures", ["name"], unique=False)
    op.create_index(op.f("ix_email_signatures_is_default"), "email_signatures", ["is_default"], unique=False)
    op.create_index(
        op.f("ix_email_signatures_account_default"),
        "email_signatures",
        ["email_account_id", "is_default"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_signatures_account_default"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_is_default"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_name"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_user_id"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_email_account_id"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_company_id"), table_name="email_signatures")
    op.drop_index(op.f("ix_email_signatures_id"), table_name="email_signatures")
    op.drop_table("email_signatures")
