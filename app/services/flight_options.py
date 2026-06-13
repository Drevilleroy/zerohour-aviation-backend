from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

SIGNAL_GREEN = "#00E5A0"


MIN_LAYOVER_MINUTES = 45
MAX_ARRIVAL_AFTER_ORIGINAL = timedelta(hours=24)


def build_rebooking_options(
    offers: list[dict[str, Any]],
    *,
    original_scheduled_arrival: datetime | None = None,
) -> list[dict[str, Any]]:
    normalized = [
        offer
        for offer in (_normalize_offer(offer) for offer in offers if offer.get("offer_id"))
        if _is_viable_offer(offer, original_scheduled_arrival)
    ]
    if not normalized:
        return []

    fastest = min(normalized, key=lambda offer: (offer["arrival_sort"], offer["price_sort"]))
    cheapest = min(normalized, key=lambda offer: (offer["price_sort"], offer["arrival_sort"]))
    recommended = max(normalized, key=lambda offer: (_balanced_score(offer, normalized), -offer["price_sort"]))

    selected = []
    seen_offer_ids = set()
    for offer, label, kind, is_default, badge_color in (
        (fastest, "Get there fastest", "fastest", False, None),
        (cheapest, "Save the most", "cheapest", False, None),
        (recommended, "ZeroHour Recommended", "recommended", True, SIGNAL_GREEN),
    ):
        if offer["offer_id"] in seen_offer_ids:
            continue
        seen_offer_ids.add(offer["offer_id"])
        selected.append(
            _present_option(
                offer,
                label=label,
                kind=kind,
                is_default=is_default,
                badge_color=badge_color,
                zerohour_recommendation_score=_balanced_score(offer, normalized),
            )
        )
    if selected and not any(option["is_default"] for option in selected):
        selected[-1]["is_default"] = True
        selected[-1]["badge_color"] = SIGNAL_GREEN
    return selected[:3]


def _normalize_offer(offer: dict[str, Any]) -> dict[str, Any]:
    departure_time = offer.get("departure_time")
    arrival_time = offer.get("arrival_time") or departure_time
    price = _decimal(offer.get("total_price", offer.get("price")))
    return {
        **offer,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "airline": offer.get("airline", "Unknown"),
        "airline_logo_url": offer.get("airline_logo_url"),
        "number_of_stops": int(offer.get("number_of_stops", offer.get("stops", 0)) or 0),
        "layovers": _normalize_layovers(offer.get("layovers", [])),
        "total_travel_time_minutes": _int_or_none(offer.get("total_travel_time_minutes")),
        "cabin_class": offer.get("cabin_class"),
        "fare_brand_name": offer.get("fare_brand_name"),
        "carry_on_allowed": offer.get("carry_on_allowed"),
        "total_price": str(price),
        "currency": offer.get("currency", "USD"),
        "arrival_sort": _timestamp(arrival_time),
        "price_sort": float(price),
    }


def _balanced_score(offer: dict[str, Any], offers: list[dict[str, Any]]) -> float:
    arrival_values = [candidate["arrival_sort"] for candidate in offers]
    price_values = [candidate["price_sort"] for candidate in offers]
    arrival_score = 1 - _normalize(offer["arrival_sort"], min(arrival_values), max(arrival_values))
    price_score = 1 - _normalize(offer["price_sort"], min(price_values), max(price_values))
    return round(arrival_score * 0.6 + price_score * 0.4, 6)


def _present_option(
    offer: dict[str, Any],
    *,
    label: str,
    kind: str,
    is_default: bool,
    badge_color: str | None,
    zerohour_recommendation_score: float,
) -> dict[str, Any]:
    return {
        "label": label,
        "kind": kind,
        "offer_id": offer["offer_id"],
        "is_default": is_default,
        "badge_color": badge_color,
        "zerohour_recommendation_score": zerohour_recommendation_score,
        "departure_time": offer["departure_time"],
        "arrival_time": offer["arrival_time"],
        "total_travel_time_minutes": offer["total_travel_time_minutes"],
        "airline": offer["airline"],
        "airline_logo_url": offer["airline_logo_url"],
        "number_of_stops": offer["number_of_stops"],
        "layovers": offer["layovers"],
        "cabin_class": offer["cabin_class"],
        "fare_warning": _fare_warning(offer),
        "total_price": offer["total_price"],
        "currency": offer["currency"],
        "flight_number": offer.get("flight_number"),
        "expires_at": offer.get("expires_at"),
    }


def _is_viable_offer(offer: dict[str, Any], original_scheduled_arrival: datetime | None) -> bool:
    if any(layover["duration_minutes"] < MIN_LAYOVER_MINUTES for layover in offer["layovers"]):
        return False
    if original_scheduled_arrival:
        arrival = _datetime(offer["arrival_time"])
        original = original_scheduled_arrival
        if original.tzinfo is None:
            original = original.replace(tzinfo=timezone.utc)
        if arrival and arrival > original + MAX_ARRIVAL_AFTER_ORIGINAL:
            return False
    if _is_basic_economy(offer) and offer.get("carry_on_allowed") is False:
        return False
    return True


def _fare_warning(offer: dict[str, Any]) -> str | None:
    if _is_basic_economy(offer):
        return "Basic economy fare"
    return None


def _is_basic_economy(offer: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "").lower()
        for value in (offer.get("cabin_class"), offer.get("fare_brand_name"), offer.get("fare_type"))
    )
    return "basic" in text and "economy" in text


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum == minimum:
        return 0.0
    return (value - minimum) / (maximum - minimum)


def _timestamp(value: str | None) -> float:
    parsed = _datetime(value)
    return parsed.timestamp() if parsed else float("inf")


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except InvalidOperation:
        return Decimal("0")


def _normalize_layovers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    layovers = []
    for item in value:
        if not isinstance(item, dict):
            continue
        layovers.append(
            {
                "airport": item.get("airport"),
                "duration_minutes": int(item.get("duration_minutes") or 0),
            }
        )
    return layovers


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
