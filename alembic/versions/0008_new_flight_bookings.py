from __future__ import annotations

"""new flight bookings

Revision ID: 0008_new_flight_bookings
Revises: 0007_aviation_scheduled_arrival
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_new_flight_bookings"
down_revision: str | None = "0007_aviation_scheduled_arrival"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("booking_id", sa.Uuid(), primary_key=True),
        sa.Column("subscriber_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("duffel_order_id", sa.String(160), nullable=False, unique=True),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.Column("destination", sa.String(8), nullable=False),
        sa.Column("flight_number", sa.String(20), nullable=False),
        sa.Column("departure_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booking_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("fare_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("zerohour_score_at_booking", sa.Integer(), nullable=False),
        sa.Column("current_zerohour_score", sa.Integer(), nullable=False),
        sa.Column("monitoring_status", sa.String(40), nullable=False, server_default="monitoring"),
        sa.Column("flight_id", sa.Uuid(), sa.ForeignKey("aviation_flights.id")),
        sa.Column("booking_confirmation", sa.String(80)),
        sa.Column("ticket_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    for column in (
        "subscriber_id",
        "duffel_order_id",
        "origin",
        "destination",
        "flight_number",
        "departure_datetime",
        "booking_timestamp",
        "monitoring_status",
        "flight_id",
        "booking_confirmation",
    ):
        op.create_index(f"ix_bookings_{column}", "bookings", [column])


def downgrade() -> None:
    for column in (
        "booking_confirmation",
        "flight_id",
        "monitoring_status",
        "booking_timestamp",
        "departure_datetime",
        "flight_number",
        "destination",
        "origin",
        "duffel_order_id",
        "subscriber_id",
    ):
        op.drop_index(f"ix_bookings_{column}", table_name="bookings")
    op.drop_table("bookings")
