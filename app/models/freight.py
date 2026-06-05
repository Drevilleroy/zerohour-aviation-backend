from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.core import uuid_pk


class Lane(Base):
    __tablename__ = "lanes"
    __table_args__ = (
        UniqueConstraint("origin_zip", "dest_zip", "trailer_type", name="uq_lane_market"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    origin_zip: Mapped[str] = mapped_column(String(10), index=True)
    dest_zip: Mapped[str] = mapped_column(String(10), index=True)
    trailer_type: Mapped[str] = mapped_column(String(40), default="van", index=True)
    current_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    predicted_rate_48hr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    rate_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    recommended_action: Mapped[str | None] = mapped_column(String(255))
    estimated_gain: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    signal_count: Mapped[int] = mapped_column(default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BrokerScore(Base):
    __tablename__ = "broker_scores"

    id: Mapped[uuid.UUID] = uuid_pk()
    broker_mc_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    broker_name: Mapped[str | None] = mapped_column(String(255))
    score: Mapped[int] = mapped_column(default=100)
    risk_level: Mapped[str] = mapped_column(String(20), default="GREEN", index=True)
    fmcsa_status: Mapped[str | None] = mapped_column(String(80))
    complaint_count: Mapped[int] = mapped_column(default=0)
    last_payment_dispute: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FuelAlert(Base):
    __tablename__ = "fuel_alerts"

    id: Mapped[uuid.UUID] = uuid_pk()
    state: Mapped[str] = mapped_column(String(2), index=True)
    corridor: Mapped[str | None] = mapped_column(String(120), index=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    predicted_price: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    predicted_change: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    hours_until: Mapped[int] = mapped_column(default=72)
    source: Mapped[str] = mapped_column(String(120), default="EIA")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DeadZone(Base):
    __tablename__ = "dead_zones"

    id: Mapped[uuid.UUID] = uuid_pk()
    market_zip: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    market_name: Mapped[str | None] = mapped_column(String(255))
    load_to_truck_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    trend: Mapped[str] = mapped_column(String(20), default="NEUTRAL")
    severity: Mapped[str] = mapped_column(String(20), default="LOW", index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    mc_number: Mapped[str | None] = mapped_column(String(40), index=True)
    carrier_name: Mapped[str | None] = mapped_column(String(255))
    home_base_zip: Mapped[str | None] = mapped_column(String(10), index=True)
    home_base_city: Mapped[str | None] = mapped_column(String(120))
    home_base_state: Mapped[str | None] = mapped_column(String(2), index=True)
    equipment_type: Mapped[str | None] = mapped_column(String(120))
    truck_count: Mapped[int] = mapped_column(Integer, default=1)
    top_lanes: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    tier: Mapped[str] = mapped_column(String(40), default="trial")
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_status: Mapped[str] = mapped_column(String(40), default="trialing", index=True)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = uuid_pk()
    lane_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lanes.id"), index=True)
    predicted_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    actual_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    accuracy_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    signal_sources: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    lane: Mapped[Lane] = relationship()


class WeeklyLoadChain(Base):
    __tablename__ = "weekly_load_chains"

    id: Mapped[uuid.UUID] = uuid_pk()
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40), default="generated", index=True)
    home_base_zip: Mapped[str] = mapped_column(String(10), index=True)
    home_base_label: Mapped[str | None] = mapped_column(String(160))
    equipment_type: Mapped[str] = mapped_column(String(120))
    truck_count: Mapped[int] = mapped_column(Integer, default=1)
    total_optimized_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    baseline_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    zerohour_advantage: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    chain_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    rendered_message: Mapped[str] = mapped_column(String(6000))
    rerouted_from_chain_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("weekly_load_chains.id")
    )
    trigger_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    operator: Mapped[Operator] = relationship()
