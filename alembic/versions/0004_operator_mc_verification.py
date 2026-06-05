from __future__ import annotations

"""operator mc verification profile fields

Revision ID: 0004_operator_mc_verification
Revises: 0003_freight_foundation
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_operator_mc_verification"
down_revision: str | None = "0003_freight_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("operators", sa.Column("carrier_name", sa.String(255), nullable=True))
    op.add_column("operators", sa.Column("home_base_city", sa.String(120), nullable=True))
    op.add_column("operators", sa.Column("home_base_state", sa.String(2), nullable=True))
    op.add_column("operators", sa.Column("equipment_type", sa.String(120), nullable=True))
    op.create_index("ix_operators_home_base_state", "operators", ["home_base_state"])


def downgrade() -> None:
    op.drop_index("ix_operators_home_base_state", table_name="operators")
    op.drop_column("operators", "equipment_type")
    op.drop_column("operators", "home_base_state")
    op.drop_column("operators", "home_base_city")
    op.drop_column("operators", "carrier_name")
