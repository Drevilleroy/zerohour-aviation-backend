from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Signal
from app.services.scoring import score_signal


def upsert_normalized_signal(
    db: Session,
    *,
    zip_code: str,
    signal_type: str,
    source: str,
    subject_hash: str,
    address_hash: str | None = None,
    event_date: date | None = None,
    confidence: Decimal = Decimal("0.50"),
    payload: dict | None = None,
) -> None:
    if isinstance(event_date, str):
        event_date = date.fromisoformat(event_date)
    if not isinstance(confidence, Decimal):
        confidence = Decimal(str(confidence))
    score = score_signal(signal_type, confidence, event_date)
    freshness_days = max((date.today() - event_date).days, 0) if event_date else 0
    signal_fired_at = datetime.now(timezone.utc)
    stmt = insert(Signal).values(
        zip_code=zip_code,
        signal_type=signal_type,
        source=source,
        subject_hash=subject_hash,
        address_hash=address_hash,
        event_date=event_date,
        freshness_days=freshness_days,
        confidence=confidence,
        score=score,
        status="active",
        payload=payload or {},
        signal_fired_at=signal_fired_at,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_signal_dedupe",
        set_={
            "zip_code": zip_code,
            "address_hash": address_hash,
            "event_date": event_date,
            "freshness_days": freshness_days,
            "confidence": confidence,
            "score": score,
            "status": "active",
            "payload": payload or {},
        },
    )
    db.execute(stmt)
