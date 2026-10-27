"""Add source_attachment_id and draft copy uniqueness constraint to email_attachments

Revision ID: 019_add_source_attachment_id
Revises: 018_campaign_steps_hardening
Create Date: 2026-10-26 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "019_add_source_attachment_id"
down_revision: Union[str, None] = "018_campaign_steps_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add nullable source_attachment_id column
    op.add_column(
        "email_attachments",
        sa.Column("source_attachment_id", sa.Integer(), nullable=True),
    )

    # 2. Add foreign key referencing email_attachments.id
    op.create_foreign_key(
        "fk_email_attachments_source_attachment_id",
        "email_attachments",
        "email_attachments",
        ["source_attachment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Create index for foreign key lookup
    op.create_index(
        "ix_email_attachments_source_attachment_id",
        "email_attachments",
        ["source_attachment_id"],
        unique=False,
    )

    # 4. Create partial unique index ensuring a source attachment can only be copied once into a given draft
    op.create_index(
        "uq_email_attachments_draft_source",
        "email_attachments",
        ["email_id", "source_attachment_id"],
        unique=True,
        postgresql_where=sa.text("source_attachment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_email_attachments_draft_source",
        table_name="email_attachments",
        postgresql_where=sa.text("source_attachment_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_email_attachments_source_attachment_id",
        table_name="email_attachments",
    )
    op.drop_constraint(
        "fk_email_attachments_source_attachment_id",
        "email_attachments",
        type_="foreignkey",
    )
    op.drop_column("email_attachments", "source_attachment_id")
