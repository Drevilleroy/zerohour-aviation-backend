from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.models import FuelAlert, Lane, Signal

EIA_DIESEL_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"


def run_fuel_pipeline(db: Session) -> dict:
    rows = _fetch_diesel_rows()
    if not rows:
        return {"status": "skipped", "reason": "no EIA rows returned"}

    created = 0
    latest_by_state = _latest_by_state(rows)
    for state, prices in latest_by_state.items():
        current = prices[-1]
        avg_4wk = sum(prices[-4:]) / Decimal(min(len(prices), 4))
        predicted_change = _predict_fuel_change(current, avg_4wk)
        alert = FuelAlert(
            state=state,
            corridor=None,
            current_price=current,
            predicted_price=current + predicted_change,
            predicted_change=predicted_change,
            hours_until=72,
            source="EIA",
            confidence=Decimal("72.00"),
        )
        db.add(alert)
        created += 1

    _emit_lane_fuel_signals(db, latest_by_state)
    db.commit()
    return {"status": "completed", "fuel_alerts_created": created}


def _fetch_diesel_rows() -> list[dict]:
    with httpx.Client(timeout=30) as client:
        response = client.get(
            EIA_DIESEL_URL,
            params={
                "product": "EMD",
                "frequency": "weekly",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": 500,
            },
        )
        response.raise_for_status()
        return response.json().get("response", {}).get("data", [])


def _latest_by_state(rows: list[dict]) -> dict[str, list[Decimal]]:
    grouped: dict[str, list[Decimal]] = {}
    for row in rows:
        state = row.get("area-name") or row.get("area") or row.get("duoarea")
        price = row.get("value")
        if not state or price in {None, ""}:
            continue
        key = str(state)[-2:].upper() if len(str(state)) > 2 else str(state).upper()
        grouped.setdefault(key, []).append(Decimal(str(price)))
    return {state: list(reversed(prices[:4])) for state, prices in grouped.items() if prices}


def _predict_fuel_change(current: Decimal, avg_4wk: Decimal) -> Decimal:
    delta = current - avg_4wk
    if delta > Decimal("0.10"):
        return Decimal("0.08")
    if delta < Decimal("-0.10"):
        return Decimal("-0.04")
    return Decimal("0.02")


def _emit_lane_fuel_signals(db: Session, latest_by_state: dict[str, list[Decimal]]) -> None:
    if not latest_by_state:
        return
    direction = (
        "UP"
        if any(
            prices[-1] > sum(prices) / Decimal(len(prices))
            for prices in latest_by_state.values()
        )
        else "NEUTRAL"
    )
    if direction == "NEUTRAL":
        return
    for lane in db.query(Lane).all():
        db.add(
            Signal(
                lane_id=lane.id,
                zip_code=lane.origin_zip,
                signal_type="FUEL",
                signal_value={"states": sorted(latest_by_state.keys())},
                source="EIA",
                direction=direction,
                weight=Decimal("0.05"),
                subject_hash=f"fuel:{lane.id}:{_bucket()}",
                confidence=Decimal("0.7200"),
                score=Decimal("0.05"),
                payload={"states": sorted(latest_by_state.keys())},
            )
        )


def _bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")
