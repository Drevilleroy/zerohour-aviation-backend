from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DeadZone, Lane, Signal

DAT_RATE_URL = "https://freight.api.dat.com/ratev2/"


def run_dat_pipeline(db: Session) -> dict:
    lanes = db.query(Lane).all()
    if not lanes or not settings.dat_api_key:
        return {
            "status": "skipped",
            "reason": "missing lanes or DAT credentials",
            "lanes": len(lanes),
        }

    updated = 0
    with httpx.Client(timeout=30) as client:
        for lane in lanes:
            payload = _fetch_rate(client, lane)
            if not payload:
                continue
            spot_rate = _decimal(payload.get("spot_rate") or payload.get("rate"))
            if spot_rate:
                previous_rate = lane.current_rate
                lane.current_rate = spot_rate
                _add_signal(
                    db,
                    lane,
                    "DAT_RATE_HISTORY",
                    payload,
                    _rate_direction(previous_rate, spot_rate),
                    Decimal("0.25"),
                )
            ratio = _decimal(payload.get("load_to_truck_ratio"))
            if ratio is not None:
                severity = dead_zone_severity(ratio)
                dead_zone = (
                    db.query(DeadZone)
                    .filter(DeadZone.market_zip == lane.origin_zip)
                    .one_or_none()
                )
                if not dead_zone:
                    dead_zone = DeadZone(market_zip=lane.origin_zip)
                    db.add(dead_zone)
                dead_zone.market_name = payload.get("origin_market")
                dead_zone.load_to_truck_ratio = ratio
                dead_zone.trend = payload.get("trend", "NEUTRAL")
                dead_zone.severity = severity
                _add_signal(
                    db,
                    lane,
                    "LOAD_TO_TRUCK",
                    {"ratio": str(ratio)},
                    _ratio_direction(ratio),
                    Decimal("0.15"),
                )
            updated += 1
    db.commit()
    return {"status": "completed", "lanes_updated": updated}


def dead_zone_severity(ratio: Decimal) -> str:
    if ratio < Decimal("1.5"):
        return "CRITICAL"
    if ratio < Decimal("2.5"):
        return "HIGH"
    if ratio < Decimal("4.0"):
        return "MED"
    return "LOW"


def _fetch_rate(client: httpx.Client, lane: Lane) -> dict:
    headers = {"Authorization": f"Bearer {settings.dat_api_key}"}
    response = client.get(
        DAT_RATE_URL,
        headers=headers,
        params={
            "originPostalCode": lane.origin_zip,
            "destinationPostalCode": lane.dest_zip,
            "equipment": lane.trailer_type,
        },
    )
    response.raise_for_status()
    return response.json()


def _add_signal(
    db: Session,
    lane: Lane,
    signal_type: str,
    value: dict,
    direction: str,
    weight: Decimal,
) -> None:
    db.add(
        Signal(
            lane_id=lane.id,
            zip_code=lane.origin_zip,
            signal_type=signal_type,
            signal_value=value,
            source="DAT",
            direction=direction,
            weight=weight,
            subject_hash=f"dat:{lane.id}:{signal_type}:{_bucket('hour')}",
            confidence=Decimal("0.8000"),
            score=weight,
            payload=value,
        )
    )


def _rate_direction(previous: Decimal | None, current: Decimal) -> str:
    if previous is None or previous <= 0:
        return "NEUTRAL"
    change = (current - previous) / previous
    if change > Decimal("0.05"):
        return "UP"
    if change < Decimal("-0.05"):
        return "DOWN"
    return "NEUTRAL"


def _ratio_direction(ratio: Decimal) -> str:
    return "UP" if ratio >= Decimal("4.0") else "DOWN" if ratio < Decimal("2.5") else "NEUTRAL"


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _bucket(grain: str) -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d%H") if grain == "hour" else now.strftime("%Y%m%d")
