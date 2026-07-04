from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import BookingHistory, DeviceToken, PriceAlert, SavedTrip, SearchAnalytics, User
from app.services.aviation_providers import DuffelClient, NotificationClient, PostmarkClient
from app.services.cache import get_json, set_json
from app.services.new_flight_booking import search_new_flight_offers

SEARCH_TIMEOUT_SECONDS = 0.45
FRESH_CACHE_SECONDS = 30
STALE_CACHE_SECONDS = 600
ZEROHOUR_REFERRAL_CODE = "ZEROHOUR_DIRECT"

CITY_TO_AIRPORT = {
    "la": "LAX",
    "los angeles": "LAX",
    "new york": "NYC",
    "nyc": "NYC",
    "san francisco": "SFO",
    "sf": "SFO",
    "chicago": "ORD",
    "miami": "MIA",
    "dallas": "DFW",
    "washington dc": "DCA",
    "washington": "DCA",
    "atlanta": "ATL",
    "seattle": "SEA",
    "boston": "BOS",
    "denver": "DEN",
    "las vegas": "LAS",
}


async def search_booking_engine(
    db: Session,
    *,
    user_id: UUID,
    departure: str,
    arrival: str,
    date: datetime,
    passengers: int,
    loyalty_number: str | None = None,
    gclid: str | None = None,
) -> dict[str, Any]:
    origin = normalize_airport(departure)
    destination = normalize_airport(arrival)
    cache_key = _search_cache_key(
        origin=origin,
        destination=destination,
        date=date,
        passengers=passengers,
        loyalty_number=loyalty_number,
    )
    cached = get_json(f"flight_search:fresh:{cache_key}")
    if cached:
        _log_search(
            db,
            user_id=user_id,
            departure=origin,
            arrival=destination,
            date=date,
            passengers=passengers,
            results_count=len(cached.get("allResults") or []),
            gclid=gclid,
            metadata={"cache": "fresh"},
        )
        return cached

    try:
        offers = await asyncio.wait_for(
            search_new_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=date,
                cabin_class="economy",
                passenger_count=passengers,
            ),
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        stale = get_json(f"flight_search:stale:{cache_key}")
        if stale:
            stale["cacheStatus"] = "stale_fallback"
            return stale
        offers = []
    except Exception as exc:
        stale = get_json(f"flight_search:stale:{cache_key}")
        if stale:
            stale["cacheStatus"] = "stale_fallback"
            return stale
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Flight search is temporarily unavailable",
        ) from exc

    envelope = build_search_envelope(
        offers,
        passengers=passengers,
        loyalty_number=loyalty_number,
    )
    envelope["cacheStatus"] = "fresh"
    set_json(f"flight_search:fresh:{cache_key}", envelope, ttl_seconds=FRESH_CACHE_SECONDS)
    set_json(f"flight_search:stale:{cache_key}", envelope, ttl_seconds=STALE_CACHE_SECONDS)
    _log_search(
        db,
        user_id=user_id,
        departure=origin,
        arrival=destination,
        date=date,
        passengers=passengers,
        results_count=len(envelope["allResults"]),
        gclid=gclid,
        metadata={"cache": "miss"},
    )
    return envelope


def build_search_envelope(
    offers: list[dict[str, Any]],
    *,
    passengers: int,
    loyalty_number: str | None = None,
) -> dict[str, Any]:
    cards = [
        _flight_card(offer, passengers=passengers, loyalty_number=loyalty_number)
        for offer in offers
    ]
    best_value = _best_value(cards)
    fastest = _pick_distinct(
        cards,
        used=[best_value],
        key=lambda card: (card["durationMinutes"], card["numberOfStops"]),
    )
    cheapest = _pick_distinct(
        cards,
        used=[best_value, fastest],
        key=lambda card: card["basePriceUsd"],
    )
    for label, card in (
        ("Best Value", best_value),
        ("Fastest", fastest),
        ("Cheapest", cheapest),
    ):
        if card and label not in card["badges"]:
            card["badges"].append(label)
    return {
        "bestValue": best_value,
        "fastest": fastest,
        "cheapest": cheapest,
        "allResults": cards,
    }


def save_trip(
    db: Session,
    *,
    user_id: UUID,
    departure: str,
    arrival: str,
    date: datetime,
    airline: str | None = None,
) -> SavedTrip:
    trip = SavedTrip(
        user_id=user_id,
        departure=normalize_airport(departure),
        arrival=normalize_airport(arrival),
        date=date,
        airline=airline,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def delete_saved_trip(db: Session, *, user_id: UUID, trip_id: UUID) -> None:
    trip = db.get(SavedTrip, trip_id)
    if not trip or str(trip.user_id) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    db.delete(trip)
    db.commit()


def set_price_alert(
    db: Session,
    *,
    user_id: UUID,
    flight_id: str,
    current_price: Decimal,
) -> PriceAlert:
    offer = (
        get_json(f"duffel:offer:{flight_id}")
        or get_json(f"duffel:search_offer:{flight_id}")
        or {}
    )
    alert = PriceAlert(
        user_id=user_id,
        flight_id=flight_id,
        current_price=current_price,
        currency=offer.get("currency") or "USD",
        departure=offer.get("origin"),
        arrival=offer.get("destination"),
        departure_date=_parse_datetime(offer.get("departure_time")),
        airline=offer.get("airline"),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def log_booking(
    db: Session,
    *,
    user_id: UUID,
    flight_id: str,
    airline: str,
    price: Decimal,
    booking_ref: str | None = None,
) -> BookingHistory:
    booking = BookingHistory(
        user_id=user_id,
        flight_id=flight_id,
        airline=airline,
        price=price,
        booking_ref=booking_ref,
        booking_date=datetime.now(UTC),
        metadata_={"source": "airline_direct", "zero_hour_commission": "0.00"},
    )
    db.add(booking)
    db.add(
        SearchAnalytics(
            user_id=user_id,
            departure="",
            arrival="",
            date=datetime.now(UTC),
            passengers=1,
            results_count=0,
            clicked_flight_id=flight_id,
            metadata_={"event": "booking_logged", "airline": airline, "price": str(price)},
        )
    )
    db.commit()
    db.refresh(booking)
    return booking


async def monitor_price_alerts(db: Session, *, limit: int = 500) -> int:
    alerts = (
        db.query(PriceAlert)
        .filter(PriceAlert.active.is_(True), PriceAlert.alert_sent_at.is_(None))
        .order_by(PriceAlert.created_at.asc())
        .limit(limit)
        .all()
    )
    sent = 0
    for alert in alerts:
        try:
            offer = await DuffelClient().get_offer(alert.flight_id)
        except Exception:
            continue
        new_price = Decimal(
            str(offer.get("total_price") or offer.get("price") or alert.current_price)
        )
        if alert.current_price - new_price <= Decimal("10"):
            continue
        user = db.get(User, alert.user_id)
        if not user:
            continue
        alert.alert_sent_at = datetime.now(UTC)
        alert.current_price = new_price
        db.commit()
        sent += 1
        message = (
            f"Price drop found for {offer.get('airline', 'your flight')}: "
            f"{new_price} {offer.get('currency') or alert.currency}. "
            "Open ZeroHour to book directly with the airline."
        )
        tokens = [
            row.token
            for row in db.query(DeviceToken)
            .filter(DeviceToken.user_id == alert.user_id, DeviceToken.active.is_(True))
            .all()
        ]
        await NotificationClient().push_user(
            tokens,
            "ZeroHour price drop",
            message,
            {"alert_id": str(alert.id), "flight_id": alert.flight_id},
        )
        await PostmarkClient().send_email(user.email, "ZeroHour price drop", message)
    return sent


def normalize_airport(value: str) -> str:
    cleaned = " ".join(value.strip().lower().split())
    if cleaned in CITY_TO_AIRPORT:
        return CITY_TO_AIRPORT[cleaned]
    compact = value.strip().upper()
    return compact if len(compact) <= 4 else compact[:3]


def _flight_card(
    offer: dict[str, Any],
    *,
    passengers: int,
    loyalty_number: str | None,
) -> dict[str, Any]:
    price = Decimal(str(offer.get("total_price") or offer.get("price") or "0"))
    duration = int(offer.get("total_travel_time_minutes") or 9999)
    booking_url = _with_tracking_params(
        offer.get("direct_booking_url") or "",
        passengers=passengers,
        loyalty_number=loyalty_number,
    )
    return {
        "flightId": offer["offer_id"],
        "airline": offer.get("airline") or "Unknown",
        "airlineLogoUrl": offer.get("airline_logo_url"),
        "flightNumber": offer.get("flight_number"),
        "departureTime": offer.get("departure_time"),
        "arrivalTime": offer.get("arrival_time"),
        "durationMinutes": duration,
        "numberOfStops": int(offer.get("number_of_stops") or 0),
        "basePriceUsd": float(price),
        "currency": offer.get("currency") or "USD",
        "directBookingUrl": booking_url,
        "availability": {
            "seatsRemaining": offer.get("available_seats"),
            "status": "available" if offer.get("available", True) else "unavailable",
        },
        "loyalty": {
            "program": _loyalty_program(offer.get("airline")),
            "numberApplied": bool(loyalty_number),
            "estimatedMiles": _estimate_miles(offer),
        },
        "badges": [],
        "zerohourScore": offer.get("zerohour_score"),
        "expiresAt": offer.get("expires_at"),
    }


def _best_value(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    viable = [card for card in cards if card["durationMinutes"] <= 480]
    pool = viable or cards
    if not pool:
        return None
    min_price = min(card["basePriceUsd"] for card in pool)
    min_duration = min(card["durationMinutes"] for card in pool)
    return min(
        pool,
        key=lambda card: (
            ((card["basePriceUsd"] - min_price) / max(min_price, 1)) * 0.65
            + ((card["durationMinutes"] - min_duration) / max(min_duration, 1)) * 0.35,
            card["numberOfStops"],
        ),
    )


def _pick_distinct(
    cards: list[dict[str, Any]],
    *,
    used: list[dict[str, Any] | None],
    key,
) -> dict[str, Any] | None:
    if not cards:
        return None
    used_ids = {card["flightId"] for card in used if card}
    pool = [card for card in cards if card["flightId"] not in used_ids] or cards
    return min(pool, key=key)


def _with_tracking_params(
    url: str,
    *,
    passengers: int,
    loyalty_number: str | None,
) -> str:
    separator = "&" if "?" in url else "?"
    params = [
        f"adults={passengers}",
        f"zh_ref={ZEROHOUR_REFERRAL_CODE}",
        "zh_commission=0",
    ]
    if loyalty_number:
        params.append(f"loyaltyNumber={loyalty_number}")
    return f"{url}{separator}{'&'.join(params)}"


def _estimate_miles(offer: dict[str, Any]) -> int | None:
    duration = offer.get("total_travel_time_minutes")
    if not duration:
        return None
    return max(250, int(duration) * 8)


def _loyalty_program(airline: str | None) -> str | None:
    if not airline:
        return None
    airline_lower = airline.lower()
    if "united" in airline_lower:
        return "MileagePlus"
    if "delta" in airline_lower:
        return "SkyMiles"
    if "american" in airline_lower:
        return "AAdvantage"
    if "alaska" in airline_lower:
        return "Mileage Plan"
    return f"{airline} loyalty"


def _search_cache_key(
    *,
    origin: str,
    destination: str,
    date: datetime,
    passengers: int,
    loyalty_number: str | None,
) -> str:
    raw = f"{origin}:{destination}:{date.date().isoformat()}:{passengers}:{loyalty_number or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _log_search(
    db: Session,
    *,
    user_id: UUID,
    departure: str,
    arrival: str,
    date: datetime,
    passengers: int,
    results_count: int,
    gclid: str | None,
    metadata: dict[str, Any],
) -> None:
    db.add(
        SearchAnalytics(
            user_id=user_id,
            departure=departure,
            arrival=arrival,
            date=date,
            passengers=passengers,
            results_count=results_count,
            gclid=gclid,
            metadata_=metadata,
        )
    )
    db.commit()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None
