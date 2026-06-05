from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

import httpx
from sqlalchemy.orm import Session

from app.models import Lane, Signal

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = ["IPMAN", "RETAILSMNSA", "DGORDER", "UMTMVS"]


def run_fred_pipeline(db: Session) -> dict:
    lanes = db.query(Lane).all()
    if not lanes:
        return {"status": "skipped", "reason": "no tracked lanes"}

    demand_score = _demand_score()
    direction = (
        "UP"
        if demand_score > Decimal("0.02")
        else "DOWN"
        if demand_score < Decimal("-0.02")
        else "NEUTRAL"
    )
    created = 0
    if direction != "NEUTRAL":
        for lane in lanes:
            db.add(
                Signal(
                    lane_id=lane.id,
                    zip_code=lane.origin_zip,
                    signal_type="FRED_DEMAND",
                    signal_value={"demand_score": str(demand_score), "series": SERIES},
                    source="FRED",
                    direction=direction,
                    weight=Decimal("0.10"),
                    subject_hash=f"fred:{lane.id}:{_bucket()}",
                    confidence=Decimal("0.6500"),
                    score=Decimal("0.10"),
                    payload={"demand_score": str(demand_score), "series": SERIES},
                )
            )
            created += 1
    db.commit()
    return {"status": "completed", "signals_created": created, "demand_score": str(demand_score)}


def _demand_score() -> Decimal:
    changes: list[Decimal] = []
    with httpx.Client(timeout=20) as client:
        for series_id in SERIES:
            response = client.get(FRED_CSV_URL, params={"id": series_id})
            response.raise_for_status()
            rows = [
                row
                for row in csv.DictReader(StringIO(response.text))
                if row.get(series_id) not in {None, "."}
            ]
            if len(rows) < 2:
                continue
            latest = Decimal(rows[-1][series_id])
            previous = Decimal(rows[-2][series_id])
            if previous:
                changes.append((latest - previous) / previous)
    if not changes:
        return Decimal("0")
    return sum(changes) / Decimal(len(changes))


def _bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")
