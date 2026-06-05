from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.db.session import get_db
from app.schemas.dashboard import DashboardResponse, ZipSignalsResponse
from app.services.cache import get_zip_signal_payload
from app.services.dashboard import get_dashboard_snapshot
from app.services.feature_flags import is_kill_switch_enabled

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> DashboardResponse:
    force_cached_mode = is_kill_switch_enabled(db, "force_cached_mode")
    snapshot_status, snapshot = get_dashboard_snapshot(db, tenant_id=ctx.tenant_id, user_id=ctx.user_id)
    message = snapshot.get("message")
    if force_cached_mode:
        message = "Using cached intelligence. Some data may still be processing."
    return DashboardResponse(
        tenant_id=ctx.tenant_id,
        mode="cached" if force_cached_mode else snapshot_status,
        message=message,
        zip_codes=snapshot.get("zip_codes", []),
        signals=snapshot.get("signals", []),
        generated_at=snapshot.get("generated_at"),
    )


@router.get("/zips/{zip_code}", response_model=ZipSignalsResponse)
def zip_signals(zip_code: str, db: Session = Depends(get_db)) -> ZipSignalsResponse:
    cache_status, payload = get_zip_signal_payload(db, zip_code)
    return ZipSignalsResponse(zip_code=zip_code, cache_status=cache_status, payload=payload)
