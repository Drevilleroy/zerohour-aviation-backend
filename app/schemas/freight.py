from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LanePredictionResponse(BaseModel):
    id: UUID
    lane_id: UUID
    origin_zip: str
    dest_zip: str
    trailer_type: str
    current_rate: Decimal | None
    predicted_rate_48hr: Decimal | None
    rate_change_pct: Decimal | None
    confidence_score: Decimal
    recommended_action: str | None
    estimated_gain: Decimal | None
    signal_count: int
    last_updated: datetime
    latest_signal_output: dict | None = None


class OperatorSignupRequest(BaseModel):
    email: EmailStr
    mc_number: str | None = None
    home_base_zip: str | None = None
    truck_count: int = Field(default=1, ge=1)
    tier: str = "trial"


class OperatorResponse(BaseModel):
    id: UUID
    email: EmailStr
    mc_number: str | None
    carrier_name: str | None
    home_base_zip: str | None
    home_base_city: str | None
    home_base_state: str | None
    equipment_type: str | None
    truck_count: int
    top_lanes: list[dict]
    tier: str
    subscription_status: str


class OperatorMcVerificationRequest(BaseModel):
    mc_number: str = Field(min_length=1, max_length=40)


class OperatorLaneRequest(BaseModel):
    origin_zip: str = Field(min_length=3, max_length=10)
    dest_zip: str = Field(min_length=3, max_length=10)
    trailer_type: str = "van"


class BrokerScoreResponse(BaseModel):
    broker_mc_number: str
    broker_name: str | None
    score: int
    risk_level: str
    fmcsa_status: str | None
    complaint_count: int
    last_payment_dispute: datetime | None
    updated_at: datetime


class FuelAlertResponse(BaseModel):
    state: str
    corridor: str | None
    current_price: Decimal
    predicted_price: Decimal
    predicted_change: Decimal
    hours_until: int
    source: str
    confidence: Decimal
    created_at: datetime


class DeadZoneResponse(BaseModel):
    market_zip: str
    market_name: str | None
    load_to_truck_ratio: Decimal
    trend: str
    severity: str
    updated_at: datetime


class SignalFeedItem(BaseModel):
    id: UUID
    lane_id: UUID | None
    signal_type: str
    signal_value: dict | None
    source: str
    direction: str
    weight: Decimal
    created_at: datetime


class TrackRecordItem(BaseModel):
    lane_id: UUID
    origin_zip: str
    dest_zip: str
    predicted_rate: Decimal
    actual_rate: Decimal | None
    accuracy_pct: Decimal | None
    signal_sources: dict
    created_at: datetime


class WeeklyLoadChainResponse(BaseModel):
    id: UUID
    operator_id: UUID
    week_start: datetime
    status: str
    home_base_zip: str
    home_base_label: str | None
    equipment_type: str
    truck_count: int
    total_optimized_revenue: Decimal
    baseline_revenue: Decimal
    zerohour_advantage: Decimal
    chain_payload: dict
    rendered_message: str
    trigger_reason: str | None
    created_at: datetime
