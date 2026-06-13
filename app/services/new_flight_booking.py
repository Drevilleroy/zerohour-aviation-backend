from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import AviationFlight, AviationUserProfile, DeviceToken, FlightBooking, User
from app.services.aviation_providers import DuffelClient, FlightAwareClient, NotificationClient, PostmarkClient, StripeClient
from app.services.aviation_scoring import score_flight_disruption_probability
from app.services.cache import get_json, set_json


async def search_new_flight_offers(
    *,
    origin: str,
    destination: str,
    departure_date: datetime,
    cabin_class: str,
    passenger_count: int,
) -> list[dict[str, Any]]:
    offers = await DuffelClient().search_alternatives(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        cabin_class=cabin_class,
        passenger_count=passenger_count,
    )
    scored = [_attach_score(offer, origin, destination, departure_date) for offer in offers]
    ranked = _rank_new_booking_offers(scored)
    for offer in ranked:
        set_json(f"duffel:search_offer:{offer['offer_id']}", offer, ttl_seconds=900)
        set_json(f"duffel:offer:{offer['offer_id']}", offer, ttl_seconds=900)
    return ranked


async def refresh_offer(offer_id: str) -> dict[str, Any]:
    initial = get_json(f"duffel:search_offer:{offer_id}")
    offer = await DuffelClient().get_offer(offer_id)
    departure = _parse_datetime(offer.get("departure_time")) or datetime.now(UTC)
    scored = _attach_score(
        offer,
        offer.get("origin") or (initial or {}).get("origin") or "",
        offer.get("destination") or (initial or {}).get("destination") or "",
        departure,
    )
    initial_price = Decimal(str((initial or {}).get("total_price", scored.get("total_price") or "0")))
    refreshed_price = Decimal(str(scored.get("total_price") or "0"))
    scored["availability_status"] = "available" if scored.get("available", True) else "unavailable"
    scored["price_changed"] = initial is not None and initial_price != refreshed_price
    if scored["price_changed"]:
        scored["warning"] = f"Price changed from {initial_price} to {refreshed_price} {scored.get('currency', 'USD')}"
    set_json(f"duffel:offer:{offer_id}", scored, ttl_seconds=900)
    return scored


async def create_new_flight_booking(
    db: Session,
    *,
    subscriber_id: UUID,
    offer_id: str,
    passenger: dict[str, Any],
    payment_token: str,
) -> FlightBooking:
    refreshed = await refresh_offer(offer_id)
    if refreshed.get("availability_status") != "available":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer is no longer available")

    user = db.get(User, subscriber_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subscriber not found")
    profile = db.get(AviationUserProfile, subscriber_id)
    if not profile or not profile.stripe_customer_id:
        customer_id = await StripeClient().create_customer(user.email, user.full_name)
        if profile:
            profile.stripe_customer_id = customer_id
            profile.active = True
        else:
            profile = AviationUserProfile(user_id=subscriber_id, stripe_customer_id=customer_id, active=True)
            db.add(profile)
        db.commit()

    amount = Decimal(str(refreshed.get("total_price") or refreshed.get("price") or "0"))
    stripe = StripeClient()
    payment_intent_id = await stripe.create_payment_intent(
        amount_cents=int(amount * 100),
        customer_id=profile.stripe_customer_id,
        idempotency_key=f"new-booking-{subscriber_id}-{offer_id}",
        description=f"ZeroHour flight booking - {refreshed.get('flight_number', offer_id)}",
        payment_method_id=payment_token,
    )

    try:
        order = await DuffelClient().create_order(offer_id, _duffel_passenger(passenger))
    except Exception:
        await stripe.cancel_payment_intent(payment_intent_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Duffel booking failed; payment cancelled")

    await stripe.confirm_payment_intent(payment_intent_id, f"new-booking-confirm-{subscriber_id}-{offer_id}")

    flight_number = order.get("new_flight_number") or refreshed.get("flight_number") or "ALT"
    departure = _parse_datetime(order.get("new_departure")) or _parse_datetime(refreshed.get("departure_time")) or datetime.now(UTC)
    origin = refreshed.get("origin") or ""
    destination = refreshed.get("destination") or ""
    score = int(refreshed.get("zerohour_score") or 0)

    webhook_id = await FlightAwareClient().register_webhook(flight_number, departure)
    flight = AviationFlight(
        user_id=subscriber_id,
        flight_number=flight_number,
        departure_date=departure,
        scheduled_arrival_time=_parse_datetime(refreshed.get("arrival_time")),
        origin=origin,
        destination=destination,
        cabin_class=refreshed.get("cabin_class") or "economy",
        flightaware_webhook_id=webhook_id,
        status="monitoring",
    )
    db.add(flight)
    db.flush()

    booking = FlightBooking(
        subscriber_id=subscriber_id,
        duffel_order_id=order["id"],
        origin=origin,
        destination=destination,
        flight_number=flight_number,
        departure_datetime=departure,
        fare_amount=amount,
        zerohour_score_at_booking=score,
        current_zerohour_score=score,
        monitoring_status="monitoring",
        flight_id=flight.id,
        booking_confirmation=order.get("pnr"),
        ticket_details=order.get("ticket_details", order),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    await send_mission_briefing(db, user, booking)
    return booking


async def get_booking_details(db: Session, *, subscriber_id: UUID, order_id: str) -> dict[str, Any]:
    booking = (
        db.query(FlightBooking)
        .filter(FlightBooking.subscriber_id == subscriber_id, FlightBooking.duffel_order_id == order_id)
        .one_or_none()
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    order = await DuffelClient().get_order(order_id)
    current_score = score_flight_disruption_probability(
        flight_number=booking.flight_number,
        origin=booking.origin,
        destination=booking.destination,
        departure_date=booking.departure_datetime,
    )
    booking.current_zerohour_score = current_score
    db.commit()
    flight_status = db.get(AviationFlight, booking.flight_id).status if booking.flight_id else "unknown"
    return {
        "booking_id": str(booking.booking_id),
        "duffel_order_id": booking.duffel_order_id,
        "booking_confirmation": booking.booking_confirmation,
        "origin": booking.origin,
        "destination": booking.destination,
        "flight_number": booking.flight_number,
        "departure_datetime": booking.departure_datetime,
        "fare_amount": str(booking.fare_amount),
        "initial_zerohour_score": booking.zerohour_score_at_booking,
        "current_zerohour_score": current_score,
        "zerohour_monitoring_status": booking.monitoring_status,
        "flight_status": flight_status,
        "duffel_order": order,
    }


async def send_mission_briefing(db: Session, user: User, booking: FlightBooking) -> None:
    message = (
        f"Flight booked. ZeroHour is now monitoring {booking.flight_number} "
        f"{booking.origin}-{booking.destination} departing {booking.departure_datetime.date()} "
        f"at {booking.departure_datetime.strftime('%H:%M')}. Current disruption probability: "
        f"{booking.current_zerohour_score}%. ZeroHour is monitoring 14 real-time data streams "
        "from now until you land. You knew before they told you."
    )
    tokens = [
        row.token
        for row in db.query(DeviceToken).filter(DeviceToken.user_id == user.id, DeviceToken.active.is_(True)).all()
    ]
    await NotificationClient().push_user(
        tokens,
        "ZeroHour mission briefing",
        message,
        {"duffel_order_id": booking.duffel_order_id, "booking_id": str(booking.booking_id)},
    )
    await PostmarkClient().send_email(user.email, "ZeroHour mission briefing", message)


def _attach_score(offer: dict[str, Any], origin: str, destination: str, departure_date: datetime) -> dict[str, Any]:
    departure = _parse_datetime(offer.get("departure_time")) or departure_date
    score = score_flight_disruption_probability(
        flight_number=offer.get("flight_number") or "ALT",
        origin=offer.get("origin") or origin,
        destination=offer.get("destination") or destination,
        departure_date=departure,
    )
    return {**offer, "zerohour_score": score}


def _rank_new_booking_offers(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not offers:
        return []
    risk_values = [float(offer.get("zerohour_score") or 0) for offer in offers]
    price_values = [float(offer.get("total_price") or offer.get("price") or 0) for offer in offers]
    for offer in offers:
        risk_score = _normalize(float(offer.get("zerohour_score") or 0), min(risk_values), max(risk_values))
        price_score = _normalize(float(offer.get("total_price") or offer.get("price") or 0), min(price_values), max(price_values))
        offer["zerohour_recommendation_score"] = round(risk_score * 0.6 + price_score * 0.4, 6)
    return sorted(
        offers,
        key=lambda offer: (
            offer["zerohour_recommendation_score"],
            float(offer.get("total_price") or offer.get("price") or 0),
            _timestamp(offer.get("arrival_time")),
        ),
    )


def _duffel_passenger(passenger: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "full_name": passenger["name"],
        "date_of_birth": passenger["date_of_birth"],
        "email": passenger["email"],
    }
    if passenger.get("phone"):
        payload["phone_number"] = passenger["phone"]
    if passenger.get("passport_number"):
        payload["passport_number"] = passenger["passport_number"]
    return payload


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum == minimum:
        return 0.0
    return (value - minimum) / (maximum - minimum)


def _timestamp(value: str | None) -> float:
    parsed = _parse_datetime(value)
    return parsed.timestamp() if parsed else float("inf")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None
