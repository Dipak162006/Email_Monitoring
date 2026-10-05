"""Add domain_id to email_accounts

Revision ID: 014_email_accounts_domain_id
Revises: 013_create_domains_table
Create Date: 2026-10-05 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "014_email_accounts_domain_id"
down_revision: Union[str, None] = "013_create_domains_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_accounts",
        sa.Column("domain_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_email_accounts_domain_id_domains",
        "email_accounts",
        "domains",
        ["domain_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_email_accounts_domain_id"),
        "email_accounts",
        ["domain_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_accounts_domain_id"), table_name="email_accounts")
    op.drop_constraint("fk_email_accounts_domain_id_domains", "email_accounts", type_="foreignkey")
    op.drop_column("email_accounts", "domain_id")
