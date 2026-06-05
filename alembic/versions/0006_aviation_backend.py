from __future__ import annotations

"""aviation backend foundation

Revision ID: 0006_aviation_backend
Revises: 0005_weekly_load_chains
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_aviation_backend"
down_revision: str | None = "0005_weekly_load_chains"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aviation_user_profiles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(120)),
        sa.Column("stripe_subscription_id", sa.String(120)),
        sa.Column("stripe_payment_method_id", sa.String(160)),
        sa.Column("plan_type", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("referring_creator_id", sa.String(120)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_aviation_user_profiles_stripe_customer_id", "aviation_user_profiles", ["stripe_customer_id"])
    op.create_index("ix_aviation_user_profiles_stripe_subscription_id", "aviation_user_profiles", ["stripe_subscription_id"])
    op.create_index("ix_aviation_user_profiles_referring_creator_id", "aviation_user_profiles", ["referring_creator_id"])
    op.create_index("ix_aviation_user_profiles_active", "aviation_user_profiles", ["active"])

    op.create_table(
        "aviation_flights",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("flight_number", sa.String(20), nullable=False),
        sa.Column("departure_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.Column("destination", sa.String(8), nullable=False),
        sa.Column("cabin_class", sa.String(40), nullable=False, server_default="economy"),
        sa.Column("flightaware_webhook_id", sa.String(160)),
        sa.Column("status", sa.String(40), nullable=False, server_default="monitoring"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("user_id", "flight_number", "departure_date", "origin", "destination", "flightaware_webhook_id", "status"):
        op.create_index(f"ix_aviation_flights_{column}", "aviation_flights", [column])

    op.create_table(
        "aviation_signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("flight_id", sa.Uuid(), sa.ForeignKey("aviation_flights.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("signal_type", sa.String(80), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("airline_announced_at", sa.DateTime(timezone=True)),
        sa.Column("head_start_minutes", sa.Integer()),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("proof_card_url", sa.Text()),
        sa.Column("high_confidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("alternatives", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("flight_id", "score", "signal_type", "confirmed"):
        op.create_index(f"ix_aviation_signals_{column}", "aviation_signals", [column])

    op.create_table(
        "aviation_bookings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.Uuid(), sa.ForeignKey("aviation_signals.id"), nullable=False),
        sa.Column("original_flight_id", sa.Uuid(), sa.ForeignKey("aviation_flights.id"), nullable=False),
        sa.Column("new_flight_number", sa.String(20), nullable=False),
        sa.Column("new_departure", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pnr", sa.String(40), nullable=False),
        sa.Column("duffel_order_id", sa.String(160), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(160), nullable=False),
        sa.Column("convenience_fee_charged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("amount_charged", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("user_id", "signal_id", "original_flight_id", "pnr", "duffel_order_id", "stripe_payment_intent_id"):
        op.create_index(f"ix_aviation_bookings_{column}", "aviation_bookings", [column])

    op.create_table(
        "aviation_passengers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Text(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("passport_number", sa.Text()),
    )
    op.create_index("ix_aviation_passengers_user_id", "aviation_passengers", ["user_id"])

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "token", name="uq_device_token_user_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_token", "device_tokens", ["token"])
    op.create_index("ix_device_tokens_active", "device_tokens", ["active"])

    op.create_table(
        "aviation_analytics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("flight_id", sa.Uuid(), sa.ForeignKey("aviation_flights.id")),
        sa.Column("signal_id", sa.Uuid(), sa.ForeignKey("aviation_signals.id")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("event_type", "user_id", "flight_id", "signal_id", "created_at"):
        op.create_index(f"ix_aviation_analytics_{column}", "aviation_analytics", [column])

    op.create_table(
        "signup_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_signup_queue_email", "signup_queue", ["email"])
    op.create_index("ix_signup_queue_status", "signup_queue", ["status"])


def downgrade() -> None:
    op.drop_index("ix_signup_queue_status", table_name="signup_queue")
    op.drop_index("ix_signup_queue_email", table_name="signup_queue")
    op.drop_table("signup_queue")
    for column in ("created_at", "signal_id", "flight_id", "user_id", "event_type"):
        op.drop_index(f"ix_aviation_analytics_{column}", table_name="aviation_analytics")
    op.drop_table("aviation_analytics")
    op.drop_index("ix_device_tokens_active", table_name="device_tokens")
    op.drop_index("ix_device_tokens_token", table_name="device_tokens")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_index("ix_aviation_passengers_user_id", table_name="aviation_passengers")
    op.drop_table("aviation_passengers")
    for column in ("stripe_payment_intent_id", "duffel_order_id", "pnr", "original_flight_id", "signal_id", "user_id"):
        op.drop_index(f"ix_aviation_bookings_{column}", table_name="aviation_bookings")
    op.drop_table("aviation_bookings")
    for column in ("confirmed", "signal_type", "score", "flight_id"):
        op.drop_index(f"ix_aviation_signals_{column}", table_name="aviation_signals")
    op.drop_table("aviation_signals")
    for column in ("status", "flightaware_webhook_id", "destination", "origin", "departure_date", "flight_number", "user_id"):
        op.drop_index(f"ix_aviation_flights_{column}", table_name="aviation_flights")
    op.drop_table("aviation_flights")
    op.drop_index("ix_aviation_user_profiles_active", table_name="aviation_user_profiles")
    op.drop_index("ix_aviation_user_profiles_referring_creator_id", table_name="aviation_user_profiles")
    op.drop_index("ix_aviation_user_profiles_stripe_subscription_id", table_name="aviation_user_profiles")
    op.drop_index("ix_aviation_user_profiles_stripe_customer_id", table_name="aviation_user_profiles")
    op.drop_table("aviation_user_profiles")
