"""booking engine account surfaces

Revision ID: 0010_booking_engine_accounts
Revises: 0009_direct_airline_handoffs
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_booking_engine_accounts"
down_revision: str | None = "0009_direct_airline_handoffs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_trips",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("departure", sa.String(80), nullable=False),
        sa.Column("arrival", sa.String(80), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("airline", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("flight_id", sa.String(160), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("departure", sa.String(80)),
        sa.Column("arrival", sa.String(80)),
        sa.Column("departure_date", sa.DateTime(timezone=True)),
        sa.Column("airline", sa.String(120)),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "booking_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("flight_id", sa.String(160), nullable=False),
        sa.Column("airline", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("booking_ref", sa.String(120)),
        sa.Column("booking_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "search_analytics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("departure", sa.String(80), nullable=False),
        sa.Column("arrival", sa.String(80), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passengers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gclid", sa.String(255)),
        sa.Column("clicked_flight_id", sa.String(160)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for table, columns in {
        "saved_trips": ("user_id", "departure", "arrival", "date", "airline"),
        "price_alerts": (
            "user_id",
            "flight_id",
            "departure",
            "arrival",
            "departure_date",
            "airline",
            "active",
        ),
        "booking_history": ("user_id", "flight_id", "airline", "booking_ref", "booking_date"),
        "search_analytics": (
            "user_id",
            "departure",
            "arrival",
            "date",
            "gclid",
            "clicked_flight_id",
        ),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, columns in {
        "search_analytics": (
            "clicked_flight_id",
            "gclid",
            "date",
            "arrival",
            "departure",
            "user_id",
        ),
        "booking_history": ("booking_date", "booking_ref", "airline", "flight_id", "user_id"),
        "price_alerts": (
            "active",
            "airline",
            "departure_date",
            "arrival",
            "departure",
            "flight_id",
            "user_id",
        ),
        "saved_trips": ("airline", "date", "arrival", "departure", "user_id"),
    }.items():
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_table("search_analytics")
    op.drop_table("booking_history")
    op.drop_table("price_alerts")
    op.drop_table("saved_trips")
