from __future__ import annotations

"""signal claim tracking and second place alerts

Revision ID: 0002_signal_claim_tracking
Revises: 0001_initial
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_signal_claim_tracking"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("second_place_shown", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "signals",
        sa.Column("signal_fired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "signals",
        sa.Column("signal_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("claimed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("claim_delta_minutes", sa.Integer(), nullable=True),
    )
    op.create_index("ix_signals_claimed_by_user_id", "signals", ["claimed_by_user_id"])
    op.create_index("ix_signals_signal_fired_at", "signals", ["signal_fired_at"])

    op.create_table(
        "second_place_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.Uuid(), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("signal_type", sa.String(80), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("claim_delta_minutes", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_second_place_alert_user_once"),
    )
    op.create_index("ix_second_place_alerts_user_id", "second_place_alerts", ["user_id"])
    op.create_index("ix_second_place_alerts_signal_id", "second_place_alerts", ["signal_id"])


def downgrade() -> None:
    op.drop_index("ix_second_place_alerts_signal_id", table_name="second_place_alerts")
    op.drop_index("ix_second_place_alerts_user_id", table_name="second_place_alerts")
    op.drop_table("second_place_alerts")
    op.drop_index("ix_signals_signal_fired_at", table_name="signals")
    op.drop_index("ix_signals_claimed_by_user_id", table_name="signals")
    op.drop_column("signals", "claim_delta_minutes")
    op.drop_column("signals", "claimed_by_user_id")
    op.drop_column("signals", "signal_claimed_at")
    op.drop_column("signals", "signal_fired_at")
    op.drop_column("users", "second_place_shown")

