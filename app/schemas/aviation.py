from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None
    plan_type: str = Field(pattern="^(monthly|annual)$")
    payment_method_id: str | None = None
    referring_creator_id: str | None = None
    passenger_full_name: str | None = None
    passenger_date_of_birth: str | None = None


class RegisterResponse(BaseModel):
    status: str
    message: str
    signup_queue_id: UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class FlightCreateRequest(BaseModel):
    flight_number: str
    departure_date: datetime
    scheduled_arrival_time: datetime | None = None
    origin: str
    destination: str
    cabin_class: str = "economy"


class FlightResponse(BaseModel):
    id: UUID
    flight_number: str
    departure_date: datetime
    scheduled_arrival_time: datetime | None
    origin: str
    destination: str
    cabin_class: str
    flightaware_webhook_id: str | None
    status: str

    model_config = {"from_attributes": True}


class DeviceRegisterRequest(BaseModel):
    token: str
    platform: str = Field(pattern="^(ios|android)$")


class BookingConfirmRequest(BaseModel):
    signal_id: UUID
    offer_id: str


class BookingResponse(BaseModel):
    id: UUID
    signal_id: UUID
    new_flight_number: str
    new_departure: datetime
    pnr: str
    duffel_order_id: str
    stripe_payment_intent_id: str
    convenience_fee_charged: bool
    amount_charged: float


class RebookingOption(BaseModel):
    label: str
    kind: str
    offer_id: str
    is_default: bool
    badge_color: str | None
    balanced_score: float
    departure_time: str | None
    arrival_time: str | None
    total_travel_time_minutes: int | None
    airline: str
    airline_logo_url: str | None = None
    number_of_stops: int
    layovers: list[dict]
    cabin_class: str | None = None
    fare_warning: str | None = None
    total_price: str
    currency: str
    flight_number: str | None = None
    expires_at: str | None = None


class SignalResponse(BaseModel):
    id: UUID
    flight_id: UUID
    score: int
    signal_type: str
    fired_at: datetime
    airline_announced_at: datetime | None
    head_start_minutes: int | None
    confirmed: bool
    proof_card_url: str | None
    alternatives: list[RebookingOption]

    model_config = {"from_attributes": True}
