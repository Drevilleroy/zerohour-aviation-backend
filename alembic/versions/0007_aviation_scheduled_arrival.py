from __future__ import annotations

"""aviation flight scheduled arrival

Revision ID: 0007_aviation_scheduled_arrival
Revises: 0006_aviation_backend
Create Date: 2026-06-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_aviation_scheduled_arrival"
down_revision: str | None = "0006_aviation_backend"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("aviation_flights", sa.Column("scheduled_arrival_time", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("aviation_flights", "scheduled_arrival_time")
