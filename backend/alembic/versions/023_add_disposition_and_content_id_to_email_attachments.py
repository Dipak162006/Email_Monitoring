"""Add disposition and content_id to email_attachments

Revision ID: 023_email_attachment_disposition
Revises: 022_incoming_protocol
Create Date: 2026-10-30 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "023_email_attachment_disposition"
down_revision: Union[str, None] = "022_incoming_protocol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("email_attachments")]

    if "disposition" not in columns:
        op.add_column(
            "email_attachments",
            sa.Column(
                "disposition",
                sa.String(length=50),
                server_default="attachment",
                nullable=False,
            ),
        )

    if "content_id" not in columns:
        op.add_column(
            "email_attachments",
            sa.Column(
                "content_id",
                sa.String(length=255),
                nullable=True,
            ),
        )

    indexes = [ix["name"] for ix in inspector.get_indexes("email_attachments")]
    if "ix_email_attachments_content_id" not in indexes:
        op.create_index(
            "ix_email_attachments_content_id",
            "email_attachments",
            ["content_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_email_attachments_content_id", table_name="email_attachments")
    op.drop_column("email_attachments", "content_id")
    op.drop_column("email_attachments", "disposition")
