from __future__ import annotations

"""freight foundation tables and signal fields

Revision ID: 0003_freight_foundation
Revises: 0002_signal_claim_tracking
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_freight_foundation"
down_revision: str | None = "0002_signal_claim_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lanes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("origin_zip", sa.String(10), nullable=False),
        sa.Column("dest_zip", sa.String(10), nullable=False),
        sa.Column("trailer_type", sa.String(40), nullable=False, server_default="van"),
        sa.Column("current_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("predicted_rate_48hr", sa.Numeric(10, 4), nullable=True),
        sa.Column("rate_change_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("confidence_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("recommended_action", sa.String(255), nullable=True),
        sa.Column("estimated_gain", sa.Numeric(12, 2), nullable=True),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("origin_zip", "dest_zip", "trailer_type", name="uq_lane_market"),
    )
    op.create_index("ix_lanes_origin_zip", "lanes", ["origin_zip"])
    op.create_index("ix_lanes_dest_zip", "lanes", ["dest_zip"])
    op.create_index("ix_lanes_trailer_type", "lanes", ["trailer_type"])

    op.add_column(
        "signals",
        sa.Column("lane_id", sa.Uuid(), sa.ForeignKey("lanes.id"), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("signal_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "signals",
        sa.Column("direction", sa.String(20), nullable=False, server_default="NEUTRAL"),
    )
    op.add_column(
        "signals",
        sa.Column("weight", sa.Numeric(6, 4), nullable=False, server_default="0"),
    )
    op.create_index("ix_signals_lane_id", "signals", ["lane_id"])
    op.create_index("ix_signals_direction", "signals", ["direction"])

    op.create_table(
        "broker_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("broker_mc_number", sa.String(40), nullable=False),
        sa.Column("broker_name", sa.String(255), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="GREEN"),
        sa.Column("fmcsa_status", sa.String(80), nullable=True),
        sa.Column("complaint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_payment_dispute", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_broker_scores_broker_mc_number",
        "broker_scores",
        ["broker_mc_number"],
        unique=True,
    )
    op.create_index("ix_broker_scores_risk_level", "broker_scores", ["risk_level"])

    op.create_table(
        "fuel_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("corridor", sa.String(120), nullable=True),
        sa.Column("current_price", sa.Numeric(8, 4), nullable=False),
        sa.Column("predicted_price", sa.Numeric(8, 4), nullable=False),
        sa.Column("predicted_change", sa.Numeric(8, 4), nullable=False),
        sa.Column("hours_until", sa.Integer(), nullable=False, server_default="72"),
        sa.Column("source", sa.String(120), nullable=False, server_default="EIA"),
        sa.Column("confidence", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_fuel_alerts_state", "fuel_alerts", ["state"])
    op.create_index("ix_fuel_alerts_corridor", "fuel_alerts", ["corridor"])
    op.create_index("ix_fuel_alerts_created_at", "fuel_alerts", ["created_at"])

    op.create_table(
        "dead_zones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("market_zip", sa.String(10), nullable=False),
        sa.Column("market_name", sa.String(255), nullable=True),
        sa.Column("load_to_truck_ratio", sa.Numeric(8, 4), nullable=False),
        sa.Column("trend", sa.String(20), nullable=False, server_default="NEUTRAL"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="LOW"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_dead_zones_market_zip", "dead_zones", ["market_zip"], unique=True)
    op.create_index("ix_dead_zones_severity", "dead_zones", ["severity"])

    op.create_table(
        "operators",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("mc_number", sa.String(40), nullable=True),
        sa.Column("home_base_zip", sa.String(10), nullable=True),
        sa.Column(
            "top_lanes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("tier", sa.String(40), nullable=False, server_default="trial"),
        sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_status", sa.String(40), nullable=False, server_default="trialing"),
    )
    op.create_index("ix_operators_email", "operators", ["email"], unique=True)
    op.create_index("ix_operators_mc_number", "operators", ["mc_number"])
    op.create_index("ix_operators_home_base_zip", "operators", ["home_base_zip"])
    op.create_index("ix_operators_subscription_status", "operators", ["subscription_status"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lane_id", sa.Uuid(), sa.ForeignKey("lanes.id"), nullable=False),
        sa.Column("predicted_rate", sa.Numeric(10, 4), nullable=False),
        sa.Column("actual_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("accuracy_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column(
            "signal_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_predictions_lane_id", "predictions", ["lane_id"])
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_predictions_created_at", table_name="predictions")
    op.drop_index("ix_predictions_lane_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_operators_subscription_status", table_name="operators")
    op.drop_index("ix_operators_home_base_zip", table_name="operators")
    op.drop_index("ix_operators_mc_number", table_name="operators")
    op.drop_index("ix_operators_email", table_name="operators")
    op.drop_table("operators")
    op.drop_index("ix_dead_zones_severity", table_name="dead_zones")
    op.drop_index("ix_dead_zones_market_zip", table_name="dead_zones")
    op.drop_table("dead_zones")
    op.drop_index("ix_fuel_alerts_created_at", table_name="fuel_alerts")
    op.drop_index("ix_fuel_alerts_corridor", table_name="fuel_alerts")
    op.drop_index("ix_fuel_alerts_state", table_name="fuel_alerts")
    op.drop_table("fuel_alerts")
    op.drop_index("ix_broker_scores_risk_level", table_name="broker_scores")
    op.drop_index("ix_broker_scores_broker_mc_number", table_name="broker_scores")
    op.drop_table("broker_scores")
    op.drop_index("ix_signals_direction", table_name="signals")
    op.drop_index("ix_signals_lane_id", table_name="signals")
    op.drop_column("signals", "weight")
    op.drop_column("signals", "direction")
    op.drop_column("signals", "signal_value")
    op.drop_column("signals", "lane_id")
    op.drop_index("ix_lanes_trailer_type", table_name="lanes")
    op.drop_index("ix_lanes_dest_zip", table_name="lanes")
    op.drop_index("ix_lanes_origin_zip", table_name="lanes")
    op.drop_table("lanes")
