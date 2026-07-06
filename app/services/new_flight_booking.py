from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import AviationFlight, DeviceToken, FlightBooking, User
from app.services.alerts import capture_critical_failure
from app.services.aviation_providers import (
    DuffelClient,
    FlightAwareClient,
    NotificationClient,
    PostmarkClient,
)
from app.services.aviation_scoring import score_flight_disruption_probability
from app.services.cache import get_json, set_json


async def search_new_flight_offers(
    *,
    origin: str,
    destination: str,
    departure_date: datetime,
    earliest_departure_time: datetime | None = None,
    latest_arrival_time: datetime | None = None,
    cabin_class: str,
    passenger_count: int,
    max_stops: int | None = None,
    nonstop_preferred: bool = False,
) -> list[dict[str, Any]]:
    offers = await DuffelClient().search_alternatives(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        cabin_class=cabin_class,
        passenger_count=passenger_count,
    )
    scored = [
        _prepare_offer(
            offer,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            earliest_departure_time=earliest_departure_time,
            latest_arrival_time=latest_arrival_time,
        )
        for offer in offers
    ]
    viable = _filter_viable_offers(
        scored,
        earliest_departure_time=earliest_departure_time,
        latest_arrival_time=latest_arrival_time,
        max_stops=max_stops,
    )
    ranked = _rank_new_booking_offers(
        viable or scored,
        latest_arrival_time=latest_arrival_time,
        nonstop_preferred=nonstop_preferred,
    )
    _label_ranked_offers(ranked)
    for offer in ranked:
        set_json(f"duffel:search_offer:{offer['offer_id']}", offer, ttl_seconds=900)
        set_json(f"duffel:offer:{offer['offer_id']}", offer, ttl_seconds=900)
    return ranked


async def refresh_offer(offer_id: str) -> dict[str, Any]:
    initial = get_json(f"duffel:search_offer:{offer_id}")
    offer = await DuffelClient().get_offer(offer_id)
    departure = _parse_datetime(offer.get("departure_time")) or datetime.now(UTC)
    scored = _prepare_offer(
        offer,
        origin=offer.get("origin") or (initial or {}).get("origin") or "",
        destination=offer.get("destination") or (initial or {}).get("destination") or "",
        departure_date=departure,
        earliest_departure_time=_parse_datetime((initial or {}).get("earliest_departure_time")),
        latest_arrival_time=_parse_datetime((initial or {}).get("latest_arrival_time")),
    )
    initial_price = Decimal(
        str((initial or {}).get("total_price", scored.get("total_price") or "0"))
    )
    refreshed_price = Decimal(str(scored.get("total_price") or "0"))
    scored["availability_status"] = "available" if scored.get("available", True) else "unavailable"
    scored["price_changed"] = initial is not None and initial_price != refreshed_price
    if scored["price_changed"]:
        scored["warning"] = (
            f"Price changed from {initial_price} to {refreshed_price} "
            f"{scored.get('currency', 'USD')}"
        )
    set_json(f"duffel:offer:{offer_id}", scored, ttl_seconds=900)
    return scored


async def create_new_flight_booking(
    db: Session,
    *,
    subscriber_id: UUID,
    offer_id: str,
    passenger: dict[str, Any] | None = None,
    payment_token: str | None = None,
) -> FlightBooking:
    refreshed = await refresh_offer(offer_id)
    if refreshed.get("availability_status") != "available":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer is no longer available",
        )

    user = db.get(User, subscriber_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subscriber not found")

    amount = Decimal(str(refreshed.get("total_price") or refreshed.get("price") or "0"))
    handoff_id = f"handoff_{uuid.uuid4().hex[:18]}"
    direct_booking_url = refreshed.get("direct_booking_url") or _build_direct_booking_url(refreshed)
    flight_number = refreshed.get("flight_number") or "ALT"
    departure = _parse_datetime(refreshed.get("departure_time")) or datetime.now(UTC)
    origin = refreshed.get("origin") or ""
    destination = refreshed.get("destination") or ""
    score = int(refreshed.get("zerohour_score") or 0)

    try:
        webhook_id = await FlightAwareClient().register_webhook(flight_number, departure)
    except Exception as exc:
        capture_critical_failure(
            "flightaware.webhook_registration_failed",
            exc,
            context={
                "subscriber_id": subscriber_id,
                "flight_number": flight_number,
                "departure": departure.isoformat(),
            },
        )
        raise
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
        duffel_order_id=handoff_id,
        origin=origin,
        destination=destination,
        flight_number=flight_number,
        departure_datetime=departure,
        fare_amount=amount,
        zerohour_score_at_booking=score,
        current_zerohour_score=score,
        monitoring_status="monitoring",
        flight_id=flight.id,
        booking_confirmation=None,
        direct_booking_url=direct_booking_url,
        booking_status="handoff_created",
        booking_source="direct_airline",
        ticket_details={
            "handoff_id": handoff_id,
            "offer": refreshed,
            "direct_booking_url": direct_booking_url,
            "fare_source": "airline_direct",
            "zero_hour_amount_charged": "0.00",
            "passenger_email": passenger.get("email") if passenger else None,
            "payment_token_ignored": bool(payment_token),
        },
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    try:
        await send_mission_briefing(db, user, booking)
    except Exception as exc:
        capture_critical_failure(
            "notifications.mission_briefing_failed",
            exc,
            context={"subscriber_id": subscriber_id, "booking_id": booking.booking_id},
        )
        raise
    return booking


async def get_booking_details(db: Session, *, subscriber_id: UUID, order_id: str) -> dict[str, Any]:
    booking = (
        db.query(FlightBooking)
        .filter(
            FlightBooking.subscriber_id == subscriber_id,
            FlightBooking.duffel_order_id == order_id,
        )
        .one_or_none()
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    current_score = score_flight_disruption_probability(
        flight_number=booking.flight_number,
        origin=booking.origin,
        destination=booking.destination,
        departure_date=booking.departure_datetime,
    )
    booking.current_zerohour_score = current_score
    db.commit()
    flight_status = (
        db.get(AviationFlight, booking.flight_id).status if booking.flight_id else "unknown"
    )
    order_payload = booking.ticket_details
    if not booking.duffel_order_id.startswith("handoff_"):
        order_payload = await DuffelClient().get_order(order_id)
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
        "direct_booking_url": booking.direct_booking_url,
        "booking_status": booking.booking_status,
        "booking_source": booking.booking_source,
        "duffel_order": order_payload,
    }


async def send_mission_briefing(db: Session, user: User, booking: FlightBooking) -> None:
    message = (
        "Flight selected. Continue directly with the airline, and ZeroHour is now monitoring "
        f"{booking.flight_number} "
        f"{booking.origin}-{booking.destination} departing {booking.departure_datetime.date()} "
        f"at {booking.departure_datetime.strftime('%H:%M')}. Current disruption probability: "
        f"{booking.current_zerohour_score}%. ZeroHour is monitoring 14 real-time data streams "
        "from now until you land. ZeroHour charged $0 for this fare handoff."
    )
    tokens = [
        row.token
        for row in db.query(DeviceToken)
        .filter(DeviceToken.user_id == user.id, DeviceToken.active.is_(True))
        .all()
    ]
    await NotificationClient().push_user(
        tokens,
        "ZeroHour mission briefing",
        message,
        {
            "handoff_id": booking.duffel_order_id,
            "booking_id": str(booking.booking_id),
            "direct_booking_url": booking.direct_booking_url or "",
        },
    )
    await PostmarkClient().send_email(user.email, "ZeroHour mission briefing", message)


def _prepare_offer(
    offer: dict[str, Any],
    *,
    origin: str,
    destination: str,
    departure_date: datetime,
    earliest_departure_time: datetime | None = None,
    latest_arrival_time: datetime | None = None,
) -> dict[str, Any]:
    departure = _parse_datetime(offer.get("departure_time")) or departure_date
    arrival = _parse_datetime(offer.get("arrival_time"))
    score = score_flight_disruption_probability(
        flight_number=offer.get("flight_number") or "ALT",
        origin=offer.get("origin") or origin,
        destination=offer.get("destination") or destination,
        departure_date=departure,
    )
    prepared = {
        **offer,
        "origin": offer.get("origin") or origin,
        "destination": offer.get("destination") or destination,
        "zerohour_score": score,
        "direct_booking_url": offer.get("direct_booking_url")
        or _build_direct_booking_url(offer | {"origin": origin, "destination": destination}),
        "booking_source": "direct_airline",
        "earliest_departure_time": (
            earliest_departure_time.isoformat() if earliest_departure_time else None
        ),
        "latest_arrival_time": latest_arrival_time.isoformat() if latest_arrival_time else None,
    }
    prepared["match_quality"] = _match_quality(
        departure=departure,
        arrival=arrival,
        earliest_departure_time=earliest_departure_time,
        latest_arrival_time=latest_arrival_time,
    )
    prepared["value_summary"] = _value_summary(prepared)
    return prepared


def _filter_viable_offers(
    offers: list[dict[str, Any]],
    *,
    earliest_departure_time: datetime | None = None,
    latest_arrival_time: datetime | None = None,
    max_stops: int | None = None,
) -> list[dict[str, Any]]:
    viable = []
    for offer in offers:
        departure = _parse_datetime(offer.get("departure_time"))
        arrival = _parse_datetime(offer.get("arrival_time"))
        stops = int(offer.get("number_of_stops") or 0)
        if earliest_departure_time and departure and departure < earliest_departure_time:
            continue
        if latest_arrival_time and arrival and arrival > latest_arrival_time:
            continue
        if max_stops is not None and stops > max_stops:
            continue
        viable.append(offer)
    return viable


def _rank_new_booking_offers(
    offers: list[dict[str, Any]],
    *,
    latest_arrival_time: datetime | None = None,
    nonstop_preferred: bool = False,
) -> list[dict[str, Any]]:
    if not offers:
        return []
    risk_values = [float(offer.get("zerohour_score") or 0) for offer in offers]
    price_values = [float(offer.get("total_price") or offer.get("price") or 0) for offer in offers]
    duration_values = [float(offer.get("total_travel_time_minutes") or 9999) for offer in offers]
    stop_values = [float(offer.get("number_of_stops") or 0) for offer in offers]
    arrival_miss_values = [_arrival_miss_minutes(offer, latest_arrival_time) for offer in offers]
    for offer in offers:
        risk_score = _normalize(
            float(offer.get("zerohour_score") or 0),
            min(risk_values),
            max(risk_values),
        )
        price_score = _normalize(
            float(offer.get("total_price") or offer.get("price") or 0),
            min(price_values),
            max(price_values),
        )
        duration_score = _normalize(
            float(offer.get("total_travel_time_minutes") or 9999),
            min(duration_values),
            max(duration_values),
        )
        stop_score = _normalize(
            float(offer.get("number_of_stops") or 0),
            min(stop_values),
            max(stop_values),
        )
        arrival_score = _normalize(
            _arrival_miss_minutes(offer, latest_arrival_time),
            min(arrival_miss_values),
            max(arrival_miss_values),
        )
        stop_weight = 0.12 if nonstop_preferred else 0.08
        offer["zerohour_recommendation_score"] = round(
            risk_score * 0.25
            + price_score * 0.15
            + duration_score * 0.16
            + arrival_score * 0.32
            + stop_score * stop_weight,
            6,
        )
    return sorted(
        offers,
        key=lambda offer: (
            offer["zerohour_recommendation_score"],
            float(offer.get("total_price") or offer.get("price") or 0),
            _timestamp(offer.get("arrival_time")),
        ),
    )


def _label_ranked_offers(offers: list[dict[str, Any]]) -> None:
    if not offers:
        return
    fastest = min(offers, key=lambda offer: float(offer.get("total_travel_time_minutes") or 9999))
    cheapest = min(
        offers,
        key=lambda offer: float(offer.get("total_price") or offer.get("price") or 0),
    )
    safest = min(offers, key=lambda offer: float(offer.get("zerohour_score") or 100))
    for index, offer in enumerate(offers):
        label = "ZeroHour Pick" if index == 0 else None
        if offer is fastest:
            label = "Fastest" if label is None else f"{label} + Fastest"
        if offer is cheapest:
            label = "Lowest Fare" if label is None else f"{label} + Lowest Fare"
        if offer is safest:
            label = "Lowest Risk" if label is None else f"{label} + Lowest Risk"
        offer["recommendation_label"] = label


def _arrival_miss_minutes(offer: dict[str, Any], latest_arrival_time: datetime | None) -> float:
    if not latest_arrival_time:
        return 0.0
    arrival = _parse_datetime(offer.get("arrival_time"))
    if not arrival:
        return 9999.0
    return max(0.0, (arrival - latest_arrival_time).total_seconds() / 60)


def _match_quality(
    *,
    departure: datetime | None,
    arrival: datetime | None,
    earliest_departure_time: datetime | None,
    latest_arrival_time: datetime | None,
) -> str:
    if earliest_departure_time and departure and departure < earliest_departure_time:
        return "departs_before_window"
    if latest_arrival_time and arrival and arrival > latest_arrival_time:
        return "arrives_after_deadline"
    if latest_arrival_time and arrival:
        buffer_minutes = int((latest_arrival_time - arrival).total_seconds() // 60)
        if buffer_minutes >= 90:
            return "arrives_with_buffer"
        if buffer_minutes >= 0:
            return "arrives_on_time"
    return "best_available"


def _value_summary(offer: dict[str, Any]) -> str:
    stops = int(offer.get("number_of_stops") or 0)
    risk = int(offer.get("zerohour_score") or 0)
    price = offer.get("total_price") or offer.get("price")
    currency = offer.get("currency") or "USD"
    stop_text = "nonstop" if stops == 0 else f"{stops} stop"
    if stops > 1:
        stop_text += "s"
    return f"{stop_text}, {risk}% disruption risk, {price} {currency} direct with airline"


AIRLINE_BOOKING_URLS = {
    "aer lingus": "https://www.aerlingus.com/html/en-US/home.html",
    "air canada": "https://www.aircanada.com/us/en/aco/home/book.html",
    "air france": "https://wwws.airfrance.us/",
    "alaska": "https://www.alaskaair.com/booking/flights",
    "american": "https://www.aa.com/booking/find-flights",
    "british airways": "https://www.britishairways.com/travel/book/public/en_us/flightList",
    "delta": "https://www.delta.com/flight-search/search",
    "frontier": "https://www.flyfrontier.com/",
    "jetblue": "https://www.jetblue.com/booking/flights",
    "klm": "https://www.klm.com/",
    "lufthansa": "https://www.lufthansa.com/us/en/homepage",
    "southwest": "https://www.southwest.com/air/booking/select.html",
    "spirit": "https://www.spirit.com/",
    "united": "https://www.united.com/en/us/fsr/choose-flights",
    "virgin atlantic": "https://www.virginatlantic.com/flight-search",
}


def _build_direct_booking_url(offer: dict[str, Any]) -> str:
    airline = str(offer.get("airline") or "").strip().lower()
    base_url = next((url for key, url in AIRLINE_BOOKING_URLS.items() if key in airline), "https://www.google.com/travel/flights")
    departure = _parse_datetime(offer.get("departure_time"))
    params = {
        "origin": offer.get("origin") or "",
        "destination": offer.get("destination") or "",
        "departureDate": departure.date().isoformat() if departure else "",
        "cabin": offer.get("cabin_class") or "economy",
        "adults": "1",
        "zh_offer": offer.get("offer_id") or "",
        "zh_source": "zero_hour_direct",
    }
    return f"{base_url}?{urlencode({key: value for key, value in params.items() if value})}"


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
