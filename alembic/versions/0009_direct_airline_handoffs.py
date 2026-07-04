"""direct airline handoffs

Revision ID: 0009_direct_airline_handoffs
Revises: 0008_new_flight_bookings
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_direct_airline_handoffs"
down_revision: str | None = "0008_new_flight_bookings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("direct_booking_url", sa.Text(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "booking_status",
            sa.String(40),
            nullable=False,
            server_default="handoff_created",
        ),
    )
    op.add_column(
        "bookings",
        sa.Column("booking_source", sa.String(40), nullable=False, server_default="direct_airline"),
    )
    op.create_index("ix_bookings_booking_status", "bookings", ["booking_status"])
    op.create_index("ix_bookings_booking_source", "bookings", ["booking_source"])


def downgrade() -> None:
    op.drop_index("ix_bookings_booking_source", table_name="bookings")
    op.drop_index("ix_bookings_booking_status", table_name="bookings")
    op.drop_column("bookings", "booking_source")
    op.drop_column("bookings", "booking_status")
    op.drop_column("bookings", "direct_booking_url")
