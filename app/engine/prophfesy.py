from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Lane, Prediction, Signal

SIGNAL_WEIGHTS = {
    "PORT_VOLUME": Decimal("0.35"),
    "DAT_RATE_HISTORY": Decimal("0.25"),
    "CARRIER_CAPACITY": Decimal("0.20"),
    "LOAD_TO_TRUCK": Decimal("0.15"),
    "WEATHER": Decimal("0.10"),
    "FRED_DEMAND": Decimal("0.10"),
    "FUEL": Decimal("0.05"),
}

DIRECTION_VALUE = {
    "STRONG_UP": Decimal("1"),
    "MODERATE_UP": Decimal("0.65"),
    "UP": Decimal("1"),
    "NEUTRAL": Decimal("0"),
    "DOWN": Decimal("-1"),
    "MODERATE_DOWN": Decimal("-0.65"),
    "STRONG_DOWN": Decimal("-1"),
}


@dataclass(frozen=True)
class ProphfesyResult:
    lane_id: str
    current_rate: Decimal
    predicted_rate: Decimal
    change_pct: Decimal
    confidence: Decimal
    window_hours: int
    action: str
    estimated_gain: Decimal
    signal_count: int
    fired: bool
    signals: list[dict[str, Any]]
    optimized_week: dict[str, Any] | None
    fired_at: datetime


def run_prophfesy_engine(db: Session, lane_id: str | None = None) -> list[ProphfesyResult]:
    query = db.query(Lane)
    if lane_id:
        query = query.filter(Lane.id == lane_id)
    results = [
        score_lane(db, lane)
        for lane in query.order_by(Lane.origin_zip, Lane.dest_zip).all()
    ]
    db.commit()
    return [result for result in results if result is not None]


def score_lane(db: Session, lane: Lane) -> ProphfesyResult | None:
    current_rate = Decimal(lane.current_rate or 0)
    if current_rate <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    signals = (
        db.query(Signal)
        .filter(Signal.lane_id == lane.id, Signal.created_at >= cutoff)
        .order_by(desc(Signal.created_at))
        .all()
    )
    if not signals:
        lane.predicted_rate_48hr = current_rate
        lane.rate_change_pct = Decimal("0")
        lane.confidence_score = Decimal("0")
        lane.recommended_action = "WATCH - waiting for fresh signals"
        lane.estimated_gain = Decimal("0")
        lane.signal_count = 0
        return None

    now = datetime.now(timezone.utc)
    weighted_sum = Decimal("0")
    total_weight = Decimal("0")
    up_count = down_count = 0
    signal_payloads: list[dict[str, Any]] = []

    for signal in signals:
        direction = _normalize_direction(signal.direction or signal.signal_type)
        direction_value = DIRECTION_VALUE[direction]
        if direction_value > 0:
            up_count += 1
        elif direction_value < 0:
            down_count += 1

        base_weight = Decimal(signal.weight or 0) or SIGNAL_WEIGHTS.get(
            signal.signal_type, Decimal("0.05")
        )
        recency_weight = _recency_weight(signal.created_at, now)
        effective_weight = base_weight * recency_weight
        weighted_sum += direction_value * effective_weight
        total_weight += effective_weight
        signal_payloads.append(
            {
                "signal_type": signal.signal_type,
                "source": signal.source,
                "direction": direction,
                "weight": str(_quantize(effective_weight, "0.0001")),
                "created_at": signal.created_at.isoformat() if signal.created_at else None,
                "value": signal.signal_value or {},
            }
        )

    if total_weight <= 0:
        return None

    direction_score = max(Decimal("-1"), min(Decimal("1"), weighted_sum / total_weight))
    agreeing_weight = sum(
        Decimal(item["weight"])
        for item in signal_payloads
        if _is_agreeing(item["direction"], direction_score)
    )
    confidence = _quantize((agreeing_weight / total_weight) * Decimal("100"), "0.01")
    same_direction_count = (
        up_count if direction_score > 0 else down_count if direction_score < 0 else 0
    )
    fired = same_direction_count >= 3

    change_pct = _quantize(direction_score * Decimal("20"), "0.01")
    predicted_rate = _quantize(
        current_rate * (Decimal("1") + (change_pct / Decimal("100"))), "0.0001"
    )
    estimated_gain = _quantize(
        max(predicted_rate - current_rate, Decimal("0")) * Decimal("1000"), "0.01"
    )
    action = _recommend_action(change_pct, confidence, fired)
    optimized_week = _optimized_week_breakdown(db, lane, current_rate, predicted_rate, action)

    lane.predicted_rate_48hr = predicted_rate
    lane.rate_change_pct = change_pct
    lane.confidence_score = confidence
    lane.recommended_action = action
    lane.estimated_gain = estimated_gain
    lane.signal_count = len(signals)
    lane.last_updated = now

    prediction = Prediction(
        lane_id=lane.id,
        predicted_rate=predicted_rate,
        signal_sources={
            "window_hours": 48,
            "direction_score": str(_quantize(direction_score, "0.0001")),
            "signals": signal_payloads,
            "fired": fired,
            "optimized_week": optimized_week,
        },
    )
    db.add(prediction)

    return ProphfesyResult(
        lane_id=str(lane.id),
        current_rate=current_rate,
        predicted_rate=predicted_rate,
        change_pct=change_pct,
        confidence=confidence,
        window_hours=48,
        action=action,
        estimated_gain=estimated_gain,
        signal_count=len(signals),
        fired=fired,
        signals=signal_payloads,
        optimized_week=optimized_week,
        fired_at=now,
    )


def calculate_prediction_accuracy(db: Session) -> int:
    pending = (
        db.query(Prediction)
        .join(Lane, Prediction.lane_id == Lane.id)
        .filter(
            Prediction.actual_rate.is_(None),
            Prediction.created_at <= datetime.now(timezone.utc) - timedelta(hours=72),
        )
        .all()
    )
    updated = 0
    for prediction in pending:
        if not prediction.lane.current_rate:
            continue
        prediction.actual_rate = prediction.lane.current_rate
        actual = Decimal(prediction.actual_rate)
        if actual > 0:
            error_pct = (
                abs((Decimal(prediction.predicted_rate) - actual) / actual) * Decimal("100")
            )
            prediction.accuracy_pct = _quantize(
                max(Decimal("0"), Decimal("100") - error_pct), "0.01"
            )
            updated += 1
    db.commit()
    return updated


def _normalize_direction(value: str) -> str:
    normalized = value.upper()
    if "STRONG_UP" in normalized:
        return "STRONG_UP"
    if "MODERATE_UP" in normalized:
        return "MODERATE_UP"
    if "UP" in normalized:
        return "UP"
    if "DOWN" in normalized:
        return "DOWN"
    return "NEUTRAL"


def _recency_weight(created_at: datetime | None, now: datetime) -> Decimal:
    if created_at is None:
        return Decimal("0.25")
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = max(Decimal("0"), Decimal((now - created_at).total_seconds()) / Decimal("3600"))
    return max(Decimal("0.25"), Decimal("1") - (age_hours / Decimal("96")))


def _is_agreeing(direction: str, direction_score: Decimal) -> bool:
    value = DIRECTION_VALUE[direction]
    return (direction_score > 0 and value > 0) or (direction_score < 0 and value < 0) or value == 0


def _recommend_action(change_pct: Decimal, confidence: Decimal, fired: bool) -> str:
    if not fired:
        return "WATCH - convergence not confirmed"
    if change_pct >= Decimal("8") and confidence >= Decimal("70"):
        return "HOLD - book inside the 48 hour window"
    if change_pct <= Decimal("-8") and confidence >= Decimal("70"):
        return "BOOK NOW - downside risk building"
    return "MONITOR - partial convergence"


def _optimized_week_breakdown(
    db: Session,
    lane: Lane,
    current_rate: Decimal,
    predicted_rate: Decimal,
    action: str,
) -> dict[str, Any] | None:
    if not action.startswith("HOLD") or not _is_long_haul(lane):
        return None

    long_haul_miles = _estimated_miles(lane.origin_zip, lane.dest_zip)
    booking_today_revenue = current_rate * long_haul_miles
    hold_revenue = predicted_rate * long_haul_miles
    short_haul_options = _short_haul_options(db, lane, current_rate)
    waiting_revenue = sum(
        Decimal(option["estimated_revenue"]) for option in short_haul_options[:2]
    )
    optimized_total = hold_revenue + waiting_revenue
    advantage = optimized_total - booking_today_revenue

    return {
        "title": "OPTIMIZED WEEK",
        "available_short_haul_options": short_haul_options,
        "short_haul_waiting_revenue": str(_quantize(waiting_revenue, "0.01")),
        "booking_today_revenue": str(_quantize(booking_today_revenue, "0.01")),
        "hold_window_revenue": str(_quantize(hold_revenue, "0.01")),
        "total_optimized_week_revenue": str(_quantize(optimized_total, "0.01")),
        "zerohour_advantage": str(_quantize(advantage, "0.01")),
        "assumptions": {
            "wait_window_hours": 48,
            "short_haul_turns": min(2, len(short_haul_options)),
            "long_haul_estimated_miles": str(long_haul_miles),
        },
    }


def _short_haul_options(db: Session, lane: Lane, fallback_rate: Decimal) -> list[dict[str, str]]:
    candidates = (
        db.query(Lane)
        .filter(Lane.origin_zip == lane.origin_zip, Lane.id != lane.id)
        .order_by(desc(Lane.current_rate))
        .limit(12)
        .all()
    )
    options = []
    for candidate in candidates:
        miles = _estimated_miles(candidate.origin_zip, candidate.dest_zip)
        if miles > Decimal("350"):
            continue
        rate = Decimal(candidate.current_rate or fallback_rate * Decimal("0.85"))
        options.append(
            _short_haul_payload(
                lane.origin_zip,
                candidate.dest_zip,
                candidate.trailer_type,
                miles,
                rate,
            )
        )
        if len(options) == 3:
            return options

    for dest_zip, miles in _synthetic_short_haul_zips(lane.origin_zip):
        if len(options) == 3:
            break
        rate = fallback_rate * Decimal("0.72")
        options.append(
            _short_haul_payload(lane.origin_zip, dest_zip, lane.trailer_type, miles, rate)
        )
    return options


def _short_haul_payload(
    origin_zip: str,
    dest_zip: str,
    trailer_type: str,
    miles: Decimal,
    rate: Decimal,
) -> dict[str, str]:
    revenue = miles * rate
    return {
        "origin_zip": origin_zip,
        "dest_zip": dest_zip,
        "trailer_type": trailer_type,
        "estimated_miles": str(_quantize(miles, "0.01")),
        "rate_per_mile": str(_quantize(rate, "0.0001")),
        "estimated_revenue": str(_quantize(revenue, "0.01")),
    }


def _is_long_haul(lane: Lane) -> bool:
    return _estimated_miles(lane.origin_zip, lane.dest_zip) >= Decimal("500")


def _estimated_miles(origin_zip: str, dest_zip: str) -> Decimal:
    try:
        origin = int(origin_zip[:3])
        dest = int(dest_zip[:3])
    except ValueError:
        return Decimal("650")
    return max(Decimal("120"), Decimal(abs(origin - dest)) * Decimal("8.5"))


def _synthetic_short_haul_zips(origin_zip: str) -> list[tuple[str, Decimal]]:
    prefix = origin_zip[:2] if len(origin_zip) >= 2 else "75"
    return [
        (f"{prefix}101", Decimal("175")),
        (f"{prefix}303", Decimal("225")),
        (f"{prefix}505", Decimal("275")),
    ]


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
