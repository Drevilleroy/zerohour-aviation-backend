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


class FlightSearchRequest(BaseModel):
    origin: str
    destination: str
    departure_date: datetime
    earliest_departure_time: datetime | None = None
    latest_arrival_time: datetime | None = None
    cabin_class: str = "economy"
    passenger_count: int = Field(default=1, ge=1, le=9)
    max_stops: int | None = Field(default=None, ge=0, le=3)
    nonstop_preferred: bool = False


class FlightOfferResponse(BaseModel):
    offer_id: str
    flight_number: str | None
    airline: str
    airline_logo_url: str | None = None
    departure_time: str | None
    arrival_time: str | None
    total_price: str
    currency: str
    number_of_stops: int
    available_seats: int | None = None
    zerohour_score: int
    zerohour_recommendation_score: float | None = None
    total_travel_time_minutes: int | None = None
    cabin_class: str | None = None
    fare_brand_name: str | None = None
    carry_on_allowed: bool | None = None
    layovers: list[dict] = []
    direct_booking_url: str | None = None
    booking_source: str = "direct_airline"
    match_quality: str | None = None
    recommendation_label: str | None = None
    value_summary: str | None = None
    expires_at: str | None = None


class OfferRefreshResponse(FlightOfferResponse):
    availability_status: str
    price_changed: bool
    warning: str | None = None


class NewBookingPassenger(BaseModel):
    name: str
    date_of_birth: str
    passport_number: str | None = None
    email: EmailStr
    phone: str | None = None


class NewFlightBookRequest(BaseModel):
    offer_id: str
    passenger: NewBookingPassenger | None = None
    payment_token: str | None = None


class NewFlightBookResponse(BaseModel):
    booking_id: UUID
    handoff_id: str
    duffel_order_id: str
    booking_confirmation: str | None
    direct_booking_url: str
    booking_source: str
    booking_status: str
    amount_charged: str = "0.00"
    ticket_details: dict
    zerohour_monitoring_active: bool
    mission_briefing_sent: bool


class FlightBookingDetailResponse(BaseModel):
    booking_id: str
    duffel_order_id: str
    booking_confirmation: str | None
    origin: str
    destination: str
    flight_number: str
    departure_datetime: datetime
    fare_amount: str
    initial_zerohour_score: int
    current_zerohour_score: int
    zerohour_monitoring_status: str
    flight_status: str
    direct_booking_url: str | None = None
    booking_status: str | None = None
    booking_source: str | None = None
    duffel_order: dict


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
    zerohour_recommendation_score: float
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
    zerohour_score: int = Field(validation_alias="score")
    signal_type: str
    fired_at: datetime
    airline_announced_at: datetime | None
    head_start_minutes: int | None
    confirmed: bool
    proof_card_url: str | None
    alternatives: list[RebookingOption]

    model_config = {"from_attributes": True}
