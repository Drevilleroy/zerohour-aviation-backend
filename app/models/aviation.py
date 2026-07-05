from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.core import uuid_pk


class AviationUserProfile(Base):
    __tablename__ = "aviation_user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    stripe_payment_method_id: Mapped[str | None] = mapped_column(String(160))
    plan_type: Mapped[str] = mapped_column(String(20), default="monthly")
    referring_creator_id: Mapped[str | None] = mapped_column(String(120), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AviationFlight(Base):
    __tablename__ = "aviation_flights"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    flight_number: Mapped[str] = mapped_column(String(20), index=True)
    departure_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scheduled_arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(String(8), index=True)
    destination: Mapped[str] = mapped_column(String(8), index=True)
    cabin_class: Mapped[str] = mapped_column(String(40), default="economy")
    flightaware_webhook_id: Mapped[str | None] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(40), default="monitoring", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class AviationSignal(Base):
    __tablename__ = "aviation_signals"

    id: Mapped[uuid.UUID] = uuid_pk()
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("aviation_flights.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    signal_type: Mapped[str] = mapped_column(String(80), index=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    airline_announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    head_start_minutes: Mapped[int | None] = mapped_column(Integer)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    proof_card_url: Mapped[str | None] = mapped_column(Text)
    high_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    alternatives: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    flight = relationship(AviationFlight)


class AviationBooking(Base):
    __tablename__ = "aviation_bookings"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("aviation_signals.id"), index=True)
    original_flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("aviation_flights.id"), index=True)
    new_flight_number: Mapped[str] = mapped_column(String(20))
    new_departure: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pnr: Mapped[str] = mapped_column(String(40), index=True)
    duffel_order_id: Mapped[str] = mapped_column(String(160), index=True)
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(160), index=True)
    convenience_fee_charged: Mapped[bool] = mapped_column(Boolean, default=False)
    amount_charged: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlightBooking(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[uuid.UUID] = uuid_pk()
    subscriber_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    duffel_order_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    origin: Mapped[str] = mapped_column(String(8), index=True)
    destination: Mapped[str] = mapped_column(String(8), index=True)
    flight_number: Mapped[str] = mapped_column(String(20), index=True)
    departure_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    booking_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    fare_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    zerohour_score_at_booking: Mapped[int] = mapped_column(Integer)
    current_zerohour_score: Mapped[int] = mapped_column(Integer)
    monitoring_status: Mapped[str] = mapped_column(String(40), default="monitoring", index=True)
    flight_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("aviation_flights.id"), index=True)
    booking_confirmation: Mapped[str | None] = mapped_column(String(80), index=True)
    direct_booking_url: Mapped[str | None] = mapped_column(Text)
    booking_status: Mapped[str] = mapped_column(String(40), default="handoff_created", index=True)
    booking_source: Mapped[str] = mapped_column(String(40), default="direct_airline", index=True)
    ticket_details: Mapped[dict] = mapped_column(JSONB, default=dict)


class SavedTrip(Base):
    __tablename__ = "saved_trips"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    flight_id: Mapped[str | None] = mapped_column(String(160), index=True)
    departure: Mapped[str] = mapped_column(String(80), index=True)
    arrival: Mapped[str] = mapped_column(String(80), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    airline: Mapped[str | None] = mapped_column(String(120), index=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    direct_booking_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    flight_id: Mapped[str] = mapped_column(String(160), index=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    departure: Mapped[str | None] = mapped_column(String(80), index=True)
    arrival: Mapped[str | None] = mapped_column(String(80), index=True)
    departure_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    airline: Mapped[str | None] = mapped_column(String(120), index=True)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class BookingHistory(Base):
    __tablename__ = "booking_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    flight_id: Mapped[str] = mapped_column(String(160), index=True)
    airline: Mapped[str] = mapped_column(String(120), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    booking_ref: Mapped[str | None] = mapped_column(String(120), index=True)
    booking_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchAnalytics(Base):
    __tablename__ = "search_analytics"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    departure: Mapped[str] = mapped_column(String(80), index=True)
    arrival: Mapped[str] = mapped_column(String(80), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    gclid: Mapped[str | None] = mapped_column(String(255), index=True)
    clicked_flight_id: Mapped[str | None] = mapped_column(String(160), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AviationPassenger(Base):
    __tablename__ = "aviation_passengers"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(320))
    passport_number: Mapped[str | None] = mapped_column(Text)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (UniqueConstraint("user_id", "token", name="uq_device_token_user_token"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(Text, index=True)
    platform: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AviationAnalytics(Base):
    __tablename__ = "aviation_analytics"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    flight_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("aviation_flights.id"), index=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("aviation_signals.id"), index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SignupQueueItem(Base):
    __tablename__ = "signup_queue"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
