"""Campaign steps, delivery step constraint, and recipient lifecycle hardening

Revision ID: 018_campaign_steps_hardening
Revises: 017_campaign_send_interval
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "018_campaign_steps_hardening"
down_revision: Union[str, None] = "017_campaign_send_interval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Create campaign_steps table
    # -------------------------------------------------------------------------
    op.create_table(
        "campaign_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("delay_hours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "step_number", name="uq_campaign_step_number"),
    )
    op.create_index(op.f("ix_campaign_steps_id"), "campaign_steps", ["id"], unique=False)
    op.create_index(op.f("ix_campaign_steps_campaign_id"), "campaign_steps", ["campaign_id"], unique=False)
    op.create_index("ix_campaign_step_order", "campaign_steps", ["campaign_id", "step_number"], unique=False)

    # -------------------------------------------------------------------------
    # 2. Backfill Step 1 for all existing campaigns
    # -------------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO campaign_steps (
            campaign_id, step_number, delay_hours, subject, body_text, body_html, is_active, created_at, updated_at
        )
        SELECT
            id,
            1,
            0,
            COALESCE(subject, 'Campaign Step 1'),
            body_text,
            body_html,
            true,
            NOW(),
            NOW()
        FROM campaigns
        """
    )

    # -------------------------------------------------------------------------
    # 3. Add step_id to campaign_deliveries & backfill
    # -------------------------------------------------------------------------
    op.add_column("campaign_deliveries", sa.Column("step_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_campaign_deliveries_step_id",
        "campaign_deliveries",
        "campaign_steps",
        ["step_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        UPDATE campaign_deliveries cd
        SET step_id = cs.id
        FROM campaign_steps cs
        WHERE cs.campaign_id = cd.campaign_id AND cs.step_number = 1
        """
    )

    # Enforce NOT NULL on step_id after successful backfill
    op.alter_column("campaign_deliveries", "step_id", nullable=False)

    # Swap unique constraint on campaign_deliveries
    op.drop_constraint("uq_campaign_delivery_recipient", "campaign_deliveries", type_="unique")
    op.create_unique_constraint(
        "uq_campaign_delivery_recipient_step",
        "campaign_deliveries",
        ["campaign_id", "recipient_id", "step_id"],
    )
    op.create_index(op.f("ix_campaign_deliveries_step_id"), "campaign_deliveries", ["step_id"], unique=False)

    # -------------------------------------------------------------------------
    # 4. Add sequence tracking columns to campaign_recipients
    # -------------------------------------------------------------------------
    op.add_column(
        "campaign_recipients",
        sa.Column("current_step_number", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("next_step_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("stopped_reason", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_campaign_recipients_next_step_due_at"),
        "campaign_recipients",
        ["next_step_due_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campaign_recipients_stopped_reason"),
        "campaign_recipients",
        ["stopped_reason"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 5. Evidence-based recipient lifecycle backfill
    # -------------------------------------------------------------------------
    # Step 5a: Suppressed recipients -> STOPPED
    op.execute(
        """
        UPDATE campaign_recipients cr
        SET status = 'STOPPED',
            stopped_reason = CASE
                WHEN sl.reason = 'BOUNCE' THEN 'BOUNCED'
                WHEN sl.reason = 'UNSUBSCRIBE' THEN 'UNSUBSCRIBED'
                ELSE 'MANUAL'
            END,
            next_step_due_at = NULL
        FROM campaigns c
        JOIN suppression_list sl ON sl.company_id = c.company_id
        WHERE c.id = cr.campaign_id AND LOWER(TRIM(sl.email)) = LOWER(TRIM(cr.email))
        """
    )

    # Step 5b: Recipients with BOUNCED deliveries -> STOPPED (BOUNCED)
    op.execute(
        """
        UPDATE campaign_recipients cr
        SET status = 'STOPPED',
            stopped_reason = 'BOUNCED',
            next_step_due_at = NULL
        WHERE cr.id IN (
            SELECT cd.recipient_id FROM campaign_deliveries cd WHERE cd.status = 'BOUNCED'
        ) AND cr.status != 'STOPPED'
        """
    )

    # Step 5c: Recipients with SENT deliveries -> COMPLETED for single-step campaigns
    op.execute(
        """
        UPDATE campaign_recipients cr
        SET status = 'COMPLETED',
            current_step_number = 1,
            next_step_due_at = NULL
        WHERE cr.id IN (
            SELECT cd.recipient_id FROM campaign_deliveries cd WHERE cd.status = 'SENT'
        ) AND cr.status != 'STOPPED'
        """
    )

    # Step 5d: Recipients in CANCELLED campaigns -> STOPPED (CAMPAIGN_CANCELLED)
    op.execute(
        """
        UPDATE campaign_recipients cr
        SET status = 'STOPPED',
            stopped_reason = 'CAMPAIGN_CANCELLED',
            next_step_due_at = NULL
        FROM campaigns c
        WHERE c.id = cr.campaign_id AND c.status = 'CANCELLED' AND cr.status NOT IN ('COMPLETED', 'STOPPED')
        """
    )

    # Step 5e: Remaining recipients (PENDING, FAILED in active/draft campaigns) -> ACTIVE
    op.execute(
        """
        UPDATE campaign_recipients
        SET status = 'ACTIVE',
            current_step_number = 0
        WHERE status NOT IN ('COMPLETED', 'STOPPED')
        """
    )


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Revert recipient status to legacy enum
    # -------------------------------------------------------------------------
    op.execute(
        """
        UPDATE campaign_recipients
        SET status = CASE
            WHEN status = 'COMPLETED' THEN 'SENT'
            WHEN status = 'STOPPED' AND stopped_reason = 'BOUNCED' THEN 'BOUNCED'
            WHEN status = 'STOPPED' AND stopped_reason = 'UNSUBSCRIBED' THEN 'SUPPRESSED'
            ELSE 'PENDING'
        END
        """
    )

    op.drop_index(op.f("ix_campaign_recipients_stopped_reason"), table_name="campaign_recipients")
    op.drop_index(op.f("ix_campaign_recipients_next_step_due_at"), table_name="campaign_recipients")
    op.drop_column("campaign_recipients", "replied_at")
    op.drop_column("campaign_recipients", "stopped_reason")
    op.drop_column("campaign_recipients", "next_step_due_at")
    op.drop_column("campaign_recipients", "current_step_number")

    # -------------------------------------------------------------------------
    # 2. Revert unique constraint on campaign_deliveries
    # -------------------------------------------------------------------------
    op.drop_index(op.f("ix_campaign_deliveries_step_id"), table_name="campaign_deliveries")
    op.drop_constraint("uq_campaign_delivery_recipient_step", "campaign_deliveries", type_="unique")
    op.create_unique_constraint(
        "uq_campaign_delivery_recipient",
        "campaign_deliveries",
        ["campaign_id", "recipient_id"],
    )
    op.drop_constraint("fk_campaign_deliveries_step_id", "campaign_deliveries", type_="foreignkey")
    op.drop_column("campaign_deliveries", "step_id")

    # -------------------------------------------------------------------------
    # 3. Drop campaign_steps table
    # -------------------------------------------------------------------------
    op.drop_index("ix_campaign_step_order", table_name="campaign_steps")
    op.drop_index(op.f("ix_campaign_steps_campaign_id"), table_name="campaign_steps")
    op.drop_index(op.f("ix_campaign_steps_id"), table_name="campaign_steps")
    op.drop_table("campaign_steps")
