"""Add incoming_protocol to email_accounts table

Revision ID: 022_incoming_protocol
Revises: 021_campaign_sending_window
Create Date: 2026-10-30 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "022_incoming_protocol"
down_revision: Union[str, None] = "021_campaign_sending_window"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add incoming_protocol column to email_accounts with server default 'IMAP'
    op.add_column(
        "email_accounts",
        sa.Column(
            "incoming_protocol",
            sa.String(length=10),
            server_default="IMAP",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("email_accounts", "incoming_protocol")

