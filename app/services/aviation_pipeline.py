from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import sentry_sdk
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.models import AviationAnalytics, AviationFlight, AviationSignal, DeviceToken
from app.services.aviation_providers import DuffelClient, NotificationClient, ProofStorageClient
from app.services.aviation_scoring import score_signal
from app.services.cache import redis_client, set_json
from app.services.circuit_breaker import CircuitBreaker
from app.services.flight_options import build_rebooking_options
from app.services.proof_card import render_proof_card_png

FLIGHTAWARE_QUEUE = "queue:flightaware:webhooks"
PROOF_CARD_QUEUE = "queue:proof_cards"


def enqueue_flightaware_webhook(payload: dict[str, Any]) -> None:
    try:
        redis_client.lpush(FLIGHTAWARE_QUEUE, json.dumps(payload, default=str))
    except RedisError as exc:
        sentry_sdk.capture_exception(exc)
        raise


async def process_flightaware_payload(db: Session, payload: dict[str, Any]) -> AviationSignal | None:
    flight = _resolve_flight(db, payload)
    if not flight:
        return None

    if _is_airline_confirmation(payload):
        await confirm_signal_from_payload(db, flight, payload)
        return None

    result = score_signal(payload)
    signal = AviationSignal(
        flight_id=flight.id,
        score=result.score,
        signal_type=result.signal_type,
        raw_payload=payload,
        high_confidence=result.high_confidence,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    if result.should_alert:
        alternatives = await find_and_cache_alternatives(flight)
        signal.alternatives = alternatives
        db.add(
            AviationAnalytics(
                event_type="signal_triggered",
                user_id=flight.user_id,
                flight_id=flight.id,
                signal_id=signal.id,
                metadata_={"score": result.score, "high_confidence": result.high_confidence},
            )
        )
        db.commit()
        await notify_signal(db, flight, signal, alternatives)
    return signal


async def drain_flightaware_queue(db: Session, limit: int = 100) -> int:
    processed = 0
    for _ in range(limit):
        raw = redis_client.rpop(FLIGHTAWARE_QUEUE)
        if not raw:
            break
        await process_flightaware_payload(db, json.loads(raw))
        processed += 1
    return processed


async def find_and_cache_alternatives(flight: AviationFlight) -> list[dict[str, Any]]:
    breaker = CircuitBreaker("duffel")
    cache_key = f"duffel:alternatives:{flight.id}"
    cached_raw = redis_client.get(cache_key)
    if breaker.is_open() and cached_raw:
        return _cached_offers(cached_raw)
    try:
        offers = await DuffelClient().search_alternatives(
            origin=flight.origin,
            destination=flight.destination,
            departure_date=flight.departure_date,
            cabin_class=flight.cabin_class,
        )
        breaker.record_success()
    except Exception as exc:
        opened = breaker.record_failure()
        sentry_sdk.capture_exception(exc)
        if cached_raw:
            return _cached_offers(cached_raw)
        if opened:
            return []
        raise

    options = build_rebooking_options(offers, original_scheduled_arrival=flight.scheduled_arrival_time)
    for offer in offers:
        ttl = _ttl_until_offer_refresh(offer.get("expires_at"))
        set_json(f"duffel:offer:{offer['offer_id']}", offer, ttl_seconds=ttl)
    set_json(cache_key, {"offers": options}, ttl_seconds=900)
    return options


async def notify_signal(
    db: Session,
    flight: AviationFlight,
    signal: AviationSignal,
    alternatives: list[dict[str, Any]],
) -> None:
    tokens = [
        row.token
        for row in db.query(DeviceToken).filter(DeviceToken.user_id == flight.user_id, DeviceToken.active.is_(True)).all()
    ]
    best = next((option for option in alternatives if option.get("is_default")), alternatives[0] if alternatives else {})
    body = (
        f"Disruption detected. {signal.score}% confidence. Best alternative: "
        f"{best.get('airline', 'pending')} arrives {best.get('arrival_time', 'soon')}. Tap to rebook."
    )
    await NotificationClient().push_user(
        tokens,
        f"ZeroHour Signal - {flight.flight_number}",
        body,
        {
            "signal_id": str(signal.id),
            "flight_id": str(flight.id),
            "offer_ids": ",".join([offer["offer_id"] for offer in alternatives]),
        },
    )


async def confirm_signal_from_payload(db: Session, flight: AviationFlight, payload: dict[str, Any]) -> None:
    signal = (
        db.query(AviationSignal)
        .filter(AviationSignal.flight_id == flight.id, AviationSignal.confirmed.is_(False))
        .order_by(AviationSignal.fired_at.desc())
        .first()
    )
    if not signal:
        return
    announced_at = _parse_datetime(payload.get("airline_announced_at")) or datetime.now(UTC)
    fired_at = signal.fired_at if signal.fired_at.tzinfo else signal.fired_at.replace(tzinfo=UTC)
    head_start = max(0, int((announced_at - fired_at).total_seconds() // 60))
    signal.airline_announced_at = announced_at
    signal.head_start_minutes = head_start
    signal.confirmed = True
    db.add(signal)
    db.add(
        AviationAnalytics(
            event_type="signal_confirmed",
            user_id=flight.user_id,
            flight_id=flight.id,
            signal_id=signal.id,
            metadata_={"head_start_minutes": head_start, "flight_number": flight.flight_number},
        )
    )
    db.commit()
    queue_proof_card(signal.id)


def queue_proof_card(signal_id: uuid.UUID) -> None:
    redis_client.lpush(PROOF_CARD_QUEUE, str(signal_id))


async def generate_proof_card(db: Session, signal_id: uuid.UUID) -> str | None:
    signal = db.get(AviationSignal, signal_id)
    if not signal or not signal.confirmed or not signal.airline_announced_at:
        return None
    flight = db.get(AviationFlight, signal.flight_id)
    if not flight:
        return None
    png = render_proof_card_png(signal, flight)
    url = await ProofStorageClient().store_png(str(signal.id), png)
    signal.proof_card_url = url
    db.add(
        AviationAnalytics(
            event_type="proof_cards_generated",
            user_id=flight.user_id,
            flight_id=flight.id,
            signal_id=signal.id,
            metadata_={
                "head_start_minutes": signal.head_start_minutes,
                "flight_number": flight.flight_number,
            },
        )
    )
    db.commit()
    hours = (signal.head_start_minutes or 0) // 60
    minutes = (signal.head_start_minutes or 0) % 60
    tokens = [
        row.token
        for row in db.query(DeviceToken).filter(DeviceToken.user_id == flight.user_id, DeviceToken.active.is_(True)).all()
    ]
    await NotificationClient().push_user(
        tokens,
        "Your proof card is ready",
        f"You knew {hours}h {minutes}m before the airline did. Your proof card is ready.",
        {"signal_id": str(signal.id), "proof_card_url": url},
    )
    return url


def _resolve_flight(db: Session, payload: dict[str, Any]) -> AviationFlight | None:
    webhook_id = payload.get("flightaware_webhook_id") or payload.get("webhook_id")
    flight_number = payload.get("flight_number") or payload.get("ident")
    query = db.query(AviationFlight)
    if webhook_id:
        return query.filter(AviationFlight.flightaware_webhook_id == str(webhook_id)).first()
    if flight_number:
        return query.filter(AviationFlight.flight_number == str(flight_number)).order_by(AviationFlight.created_at.desc()).first()
    return None


def _cached_offers(raw: str) -> list[dict[str, Any]]:
    value = json.loads(raw)
    return value.get("offers", value) if isinstance(value, dict) else value


def _is_airline_confirmation(payload: dict[str, Any]) -> bool:
    event_type = str(payload.get("event_type") or payload.get("status") or "").lower()
    return event_type in {"cancelled", "canceled", "delayed", "airline_confirmed_delay", "airline_confirmed_cancel"}


def _ttl_until_offer_refresh(expires_at: str | None) -> int:
    expires = _parse_datetime(expires_at)
    if not expires:
        return 900
    return max(60, int((expires - datetime.now(UTC)).total_seconds()) - 300)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None
