"""Add partial unique index for single default signature per email account

Revision ID: 010_unique_default_signature
Revises: 009_create_email_signatures
Create Date: 2026-09-16 09:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_unique_default_signature"
down_revision: Union[str, None] = "009_create_email_signatures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create PostgreSQL partial unique index ensuring at most one default signature per account
    op.create_index(
        "uq_email_signatures_account_default",
        "email_signatures",
        ["email_account_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_email_signatures_account_default",
        table_name="email_signatures",
        postgresql_where=sa.text("is_default = true"),
    )
