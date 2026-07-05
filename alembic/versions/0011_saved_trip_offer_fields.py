"""saved trip offer fields

Revision ID: 0011_saved_trip_offer_fields
Revises: 0010_booking_engine_accounts
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_saved_trip_offer_fields"
down_revision: str | None = "0010_booking_engine_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("saved_trips", sa.Column("flight_id", sa.String(160)))
    op.add_column("saved_trips", sa.Column("price", sa.Numeric(12, 2)))
    op.add_column(
        "saved_trips",
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
    )
    op.add_column("saved_trips", sa.Column("direct_booking_url", sa.Text()))
    op.create_index("ix_saved_trips_flight_id", "saved_trips", ["flight_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_trips_flight_id", table_name="saved_trips")
    op.drop_column("saved_trips", "direct_booking_url")
    op.drop_column("saved_trips", "currency")
    op.drop_column("saved_trips", "price")
    op.drop_column("saved_trips", "flight_id")
