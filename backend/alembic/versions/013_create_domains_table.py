"""Create domains table

Revision ID: 013_create_domains_table
Revises: 012_create_company_invitations
Create Date: 2026-10-05 12:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013_create_domains_table"
down_revision: Union[str, None] = "012_create_company_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(length=255), nullable=False),
        sa.Column("verification_status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("spf_status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("dkim_status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("dmarc_status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("mx_status", sa.String(length=50), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("dkim_selector", sa.String(length=100), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_error", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "domain_name", name="uq_company_domain_name"),
    )
    op.create_index(op.f("ix_domains_id"), "domains", ["id"], unique=False)
    op.create_index(op.f("ix_domains_company_id"), "domains", ["company_id"], unique=False)
    op.create_index(op.f("ix_domains_domain_name"), "domains", ["domain_name"], unique=False)
    op.create_index(op.f("ix_domains_verification_status"), "domains", ["verification_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_domains_verification_status"), table_name="domains")
    op.drop_index(op.f("ix_domains_domain_name"), table_name="domains")
    op.drop_index(op.f("ix_domains_company_id"), table_name="domains")
    op.drop_index(op.f("ix_domains_id"), table_name="domains")
    op.drop_table("domains")
