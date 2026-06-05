from __future__ import annotations

"""weekly load chain engine persistence

Revision ID: 0005_weekly_load_chains
Revises: 0004_operator_mc_verification
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_weekly_load_chains"
down_revision: str | None = "0004_operator_mc_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operators",
        sa.Column("truck_count", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "weekly_load_chains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operator_id", sa.Uuid(), sa.ForeignKey("operators.id"), nullable=False),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="generated"),
        sa.Column("home_base_zip", sa.String(10), nullable=False),
        sa.Column("home_base_label", sa.String(160), nullable=True),
        sa.Column("equipment_type", sa.String(120), nullable=False),
        sa.Column("truck_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_optimized_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("baseline_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("zerohour_advantage", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("chain_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rendered_message", sa.String(6000), nullable=False),
        sa.Column("rerouted_from_chain_id", sa.Uuid(), sa.ForeignKey("weekly_load_chains.id")),
        sa.Column("trigger_reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_weekly_load_chains_operator_id", "weekly_load_chains", ["operator_id"])
    op.create_index("ix_weekly_load_chains_week_start", "weekly_load_chains", ["week_start"])
    op.create_index("ix_weekly_load_chains_status", "weekly_load_chains", ["status"])
    op.create_index("ix_weekly_load_chains_home_base_zip", "weekly_load_chains", ["home_base_zip"])
    op.create_index("ix_weekly_load_chains_created_at", "weekly_load_chains", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_weekly_load_chains_created_at", table_name="weekly_load_chains")
    op.drop_index("ix_weekly_load_chains_home_base_zip", table_name="weekly_load_chains")
    op.drop_index("ix_weekly_load_chains_status", table_name="weekly_load_chains")
    op.drop_index("ix_weekly_load_chains_week_start", table_name="weekly_load_chains")
    op.drop_index("ix_weekly_load_chains_operator_id", table_name="weekly_load_chains")
    op.drop_table("weekly_load_chains")
    op.drop_column("operators", "truck_count")
