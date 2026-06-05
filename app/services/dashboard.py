from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Territory
from app.services.cache import CacheKeys, get_json, get_zip_signal_payload, set_json


def build_dashboard_snapshot(db: Session, *, tenant_id: UUID, user_id: UUID) -> dict:
    territories = db.query(Territory).filter(Territory.tenant_id == tenant_id).all()
    zip_codes = [territory.zip_code for territory in territories]
    signals: list[dict] = []
    cache_statuses: dict[str, str] = {}
    generated_at = None

    for zip_code in zip_codes[:25]:
        cache_status, payload = get_zip_signal_payload(db, zip_code)
        cache_statuses[zip_code] = cache_status
        signals.extend(payload.get("signals", [])[:20])
        generated_at = payload.get("generated_at") or generated_at

    mode = "ready" if signals else "empty_state"
    message = None
    if not zip_codes:
        message = "Add ZIP codes to start monitoring seller-signal intelligence."
    elif not signals:
        message = "Initial intelligence is processing. The dashboard will fill from cached ZIP datasets."

    snapshot = {
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "mode": mode,
        "message": message,
        "zip_codes": zip_codes,
        "signals": signals,
        "cache_statuses": cache_statuses,
        "generated_at": generated_at,
    }
    set_json(CacheKeys.user_dashboard(str(user_id)), snapshot, ttl_seconds=600)
    return snapshot


def get_dashboard_snapshot(db: Session, *, tenant_id: UUID, user_id: UUID) -> tuple[str, dict]:
    cached = get_json(CacheKeys.user_dashboard(str(user_id)))
    if cached:
        return "redis_snapshot", cached
    return "rebuilt_from_zip_cache", build_dashboard_snapshot(db, tenant_id=tenant_id, user_id=user_id)
