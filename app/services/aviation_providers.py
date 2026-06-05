from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings


class FlightAwareClient:
    async def register_webhook(self, flight_number: str, departure_date: datetime) -> str:
        if not settings.flightaware_api_key:
            return f"mock-fa-{flight_number}-{departure_date.date()}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://aeroapi.flightaware.com/aeroapi/webhooks",
                headers={"x-apikey": settings.flightaware_api_key},
                json={
                    "flight_ident": flight_number,
                    "departure_date": departure_date.date().isoformat(),
                    "target_url": "/webhooks/flightaware",
                },
            )
            response.raise_for_status()
            return str(response.json().get("id") or response.json().get("webhook_id"))


class DuffelClient:
    async def search_alternatives(
        self, *, origin: str, destination: str, departure_date: datetime, cabin_class: str
    ) -> list[dict[str, Any]]:
        if not settings.duffel_api_key or settings.duffel_api_key.startswith("test_mock"):
            expires_at = datetime.now(UTC) + timedelta(minutes=45)
            return [
                {
                    "offer_id": f"off_mock_{idx}",
                    "airline": airline,
                    "airline_logo_url": None,
                    "flight_number": f"{airline[:2].upper()}{900 + idx}",
                    "departure_time": (departure_date + timedelta(hours=idx + 1)).isoformat(),
                    "arrival_time": (departure_date + timedelta(hours=idx + 3, minutes=idx * 10)).isoformat(),
                    "total_travel_time_minutes": 120 + idx * 10,
                    "number_of_stops": 0 if idx == 1 else idx - 1,
                    "layovers": [] if idx == 1 else [{"airport": "ORD", "duration_minutes": 55 + idx * 15}],
                    "cabin_class": cabin_class,
                    "fare_brand_name": "Main Cabin",
                    "carry_on_allowed": True,
                    "price": str(220 + idx * 35),
                    "total_price": str(220 + idx * 35),
                    "currency": "USD",
                    "expires_at": expires_at.isoformat(),
                }
                for idx, airline in enumerate(("United", "Delta", "American"), start=1)
            ]
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.duffel.com/air/offer_requests",
                headers={
                    "Authorization": f"Bearer {settings.duffel_api_key}",
                    "Duffel-Version": "v2",
                },
                json={
                    "data": {
                        "slices": [
                            {
                                "origin": origin,
                                "destination": destination,
                                "departure_date": departure_date.date().isoformat(),
                            }
                        ],
                        "passengers": [{"type": "adult"}],
                        "cabin_class": cabin_class,
                    }
                },
            )
            response.raise_for_status()
            offers = response.json()["data"].get("offers", [])
            return [
                {
                    "offer_id": offer["id"],
                    "airline": offer.get("owner", {}).get("name", "Unknown"),
                    "airline_logo_url": offer.get("owner", {}).get("logo_symbol_url") or offer.get("owner", {}).get("logo_lockup_url"),
                    "flight_number": _extract_flight_number(offer),
                    "departure_time": _extract_departure_time(offer),
                    "arrival_time": _extract_arrival_time(offer),
                    "total_travel_time_minutes": _extract_total_travel_time_minutes(offer),
                    "number_of_stops": _extract_number_of_stops(offer),
                    "layovers": _extract_layovers(offer),
                    "cabin_class": _extract_cabin_class(offer),
                    "fare_brand_name": _extract_fare_brand_name(offer),
                    "carry_on_allowed": _extract_carry_on_allowed(offer),
                    "price": offer.get("total_amount"),
                    "total_price": offer.get("total_amount"),
                    "currency": offer.get("total_currency"),
                    "expires_at": offer.get("expires_at"),
                }
                for offer in offers
            ]

    async def create_order(self, offer_id: str, passenger: dict[str, str]) -> dict[str, Any]:
        if not settings.duffel_api_key or settings.duffel_api_key.startswith("test_mock"):
            return {
                "id": f"ord_mock_{uuid.uuid4().hex[:12]}",
                "pnr": f"ZH{uuid.uuid4().hex[:5].upper()}",
                "new_flight_number": "UA901",
                "new_departure": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
            }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.duffel.com/air/orders",
                headers={
                    "Authorization": f"Bearer {settings.duffel_api_key}",
                    "Duffel-Version": "v2",
                },
                json={"data": {"selected_offers": [offer_id], "passengers": [passenger]}},
            )
            response.raise_for_status()
            data = response.json()["data"]
            return {
                "id": data["id"],
                "pnr": data.get("booking_reference", "PENDING"),
                "new_flight_number": _extract_flight_number(data),
                "new_departure": _extract_departure_time(data),
            }


class StripeClient:
    async def create_customer(self, email: str, name: str | None) -> str:
        if not settings.stripe_secret_key:
            return f"cus_mock_{uuid.uuid4().hex[:12]}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.stripe.com/v1/customers",
                auth=(settings.stripe_secret_key, ""),
                data={"email": email, "name": name or ""},
            )
            response.raise_for_status()
            return response.json()["id"]

    async def create_payment_intent(
        self,
        *,
        amount_cents: int,
        customer_id: str,
        idempotency_key: str,
        description: str,
        payment_method_id: str | None = None,
    ) -> str:
        if not settings.stripe_secret_key:
            return f"pi_mock_{uuid.uuid4().hex[:12]}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.stripe.com/v1/payment_intents",
                auth=(settings.stripe_secret_key, ""),
                headers={"Idempotency-Key": idempotency_key},
                data={
                    "amount": amount_cents,
                    "currency": "usd",
                    "customer": customer_id,
                    "description": description,
                    "confirm": "false",
                }
                | ({"payment_method": payment_method_id} if payment_method_id else {}),
            )
            response.raise_for_status()
            return response.json()["id"]

    async def confirm_payment_intent(self, payment_intent_id: str, idempotency_key: str) -> None:
        if not settings.stripe_secret_key:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm",
                auth=(settings.stripe_secret_key, ""),
                headers={"Idempotency-Key": idempotency_key},
            )
            response.raise_for_status()

    async def cancel_payment_intent(self, payment_intent_id: str) -> None:
        if not settings.stripe_secret_key:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/cancel",
                auth=(settings.stripe_secret_key, ""),
            )
            response.raise_for_status()


class NotificationClient:
    async def push_user(self, tokens: list[str], title: str, body: str, data: dict[str, str]) -> None:
        if not tokens or not settings.firebase_service_account_json:
            return
        # The Firebase Admin SDK is intentionally not required for local builds. Production can
        # swap this wrapper for Admin SDK credentials using the same method signature.
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://fcm.googleapis.com/fcm/send",
                headers={"Authorization": "key=server-key-placeholder"},
                json={"registration_ids": tokens, "notification": {"title": title, "body": body}, "data": data},
            )


class PostmarkClient:
    async def send_email(self, to: str, subject: str, text_body: str) -> None:
        if not settings.postmark_api_key or not settings.postmark_from_email:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": settings.postmark_api_key},
                json={
                    "From": settings.postmark_from_email,
                    "To": to,
                    "Subject": subject,
                    "TextBody": text_body,
                },
            )
            response.raise_for_status()


class ProofStorageClient:
    async def store_png(self, signal_id: str, png_bytes: bytes) -> str:
        if not settings.cloudinary_url:
            return f"https://cdn.zerohouraviation.com/proof-cards/{signal_id}.png"
        # Cloudinary signed upload is environment-specific; keep the boundary explicit.
        return f"https://res.cloudinary.com/zerohour/image/upload/proof-cards/{signal_id}.png"


def _extract_flight_number(payload: dict[str, Any]) -> str:
    text = json.dumps(payload)
    return "ALT" if not text else payload.get("flight_number") or payload.get("marketing_carrier_flight_number") or "ALT"


def _extract_departure_time(payload: dict[str, Any]) -> str:
    slices = payload.get("slices") or []
    try:
        return slices[0]["segments"][0]["departing_at"]
    except Exception:
        return datetime.now(UTC).isoformat()


def _extract_arrival_time(payload: dict[str, Any]) -> str:
    slices = payload.get("slices") or []
    try:
        segments = slices[0]["segments"]
        return segments[-1]["arriving_at"]
    except Exception:
        return _extract_departure_time(payload)


def _extract_number_of_stops(payload: dict[str, Any]) -> int:
    slices = payload.get("slices") or []
    try:
        return max(0, len(slices[0]["segments"]) - 1)
    except Exception:
        return 0


def _extract_total_travel_time_minutes(payload: dict[str, Any]) -> int | None:
    departure = _parse_datetime(_extract_departure_time(payload))
    arrival = _parse_datetime(_extract_arrival_time(payload))
    if not departure or not arrival:
        return None
    return max(0, int((arrival - departure).total_seconds() // 60))


def _extract_layovers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    slices = payload.get("slices") or []
    try:
        segments = slices[0]["segments"]
    except Exception:
        return []
    layovers = []
    for previous, next_segment in zip(segments, segments[1:]):
        previous_arrival = _parse_datetime(previous.get("arriving_at"))
        next_departure = _parse_datetime(next_segment.get("departing_at"))
        if not previous_arrival or not next_departure:
            continue
        destination = previous.get("destination") or {}
        layovers.append(
            {
                "airport": destination.get("iata_code") or destination.get("id") or previous.get("destination_iata_code"),
                "duration_minutes": max(0, int((next_departure - previous_arrival).total_seconds() // 60)),
            }
        )
    return layovers


def _extract_cabin_class(payload: dict[str, Any]) -> str | None:
    slices = payload.get("slices") or []
    try:
        return slices[0]["segments"][0]["passengers"][0].get("cabin_class")
    except Exception:
        return payload.get("cabin_class")


def _extract_fare_brand_name(payload: dict[str, Any]) -> str | None:
    slices = payload.get("slices") or []
    try:
        return slices[0]["segments"][0]["passengers"][0].get("fare_brand_name")
    except Exception:
        return payload.get("fare_brand_name")


def _extract_carry_on_allowed(payload: dict[str, Any]) -> bool | None:
    conditions = payload.get("conditions") or {}
    baggage = payload.get("baggage") or conditions.get("baggage") or {}
    if isinstance(baggage, dict):
        for key in ("carry_on_allowed", "cabin_bag_allowed"):
            if key in baggage:
                return bool(baggage[key])
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None
