from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any


WEIGHTS = {
    "crew_scheduling_pressure": 25,
    "maintenance_flag": 20,
    "weather_system_trajectory": 20,
    "atc_congestion": 15,
    "ground_stop": 10,
    "historical_delay_rate": 10,
}


@dataclass(frozen=True)
class ProphfesyResult:
    score: int
    signal_type: str
    high_confidence: bool
    should_alert: bool


def score_signal(payload: dict[str, Any]) -> ProphfesyResult:
    indicators = payload.get("indicators") or payload.get("signals") or {}
    score = 0
    fired = []
    for key, weight in WEIGHTS.items():
        value = indicators.get(key, 0)
        normalized = _normalize_indicator(value)
        if normalized > 0:
            fired.append(key)
        score += round(weight * normalized)
    score = max(0, min(100, score))
    return ProphfesyResult(
        score=score,
        signal_type="+".join(fired) if fired else payload.get("event_type", "flightaware_event"),
        high_confidence=score >= 85,
        should_alert=score >= 70,
    )


def score_flight_disruption_probability(
    *,
    flight_number: str,
    origin: str,
    destination: str,
    departure_date: datetime,
) -> int:
    """Deterministic pre-booking risk proxy until live flight signals arrive."""
    fingerprint = sha256(
        f"{flight_number.upper()}:{origin.upper()}:{destination.upper()}:{departure_date.date()}".encode()
    ).digest()
    route_pressure = fingerprint[0] / 255
    time_pressure = 0.2 if departure_date.hour in {6, 7, 8, 16, 17, 18, 19} else 0.0
    day_pressure = 0.15 if departure_date.weekday() in {0, 4, 6} else 0.0
    score = round((route_pressure * 0.65 + time_pressure + day_pressure) * 100)
    return max(1, min(99, score))


def _normalize_indicator(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "high", "severe", "ground_stop"}:
            return 1.0
        if lowered in {"medium", "moderate"}:
            return 0.6
        if lowered in {"low", "minor"}:
            return 0.3
    return 0.0
