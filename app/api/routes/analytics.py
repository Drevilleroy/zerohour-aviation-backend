from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import UnitEconomicsSnapshot
from app.schemas.common import EventCaptureRequest, StatusResponse
from app.services.telemetry import capture_behavioral_event

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events", response_model=StatusResponse)
def capture_event(payload: EventCaptureRequest, db: Session = Depends(get_db)) -> StatusResponse:
    capture_behavioral_event(
        db,
        event_type=payload.event_type,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        properties=payload.properties,
    )
    db.commit()
    return StatusResponse(status="recorded")


@router.get("/unit-economics")
def unit_economics_summary(db: Session = Depends(get_db)) -> dict:
    rows = db.query(UnitEconomicsSnapshot).order_by(UnitEconomicsSnapshot.captured_at.desc()).limit(50).all()
    return {
        "status": "ready",
        "metrics": [
            "revenue_per_user",
            "infrastructure_cost_per_user",
            "api_cost_per_zip",
            "signal_cost_per_market",
            "creator_cac",
            "payback_period",
            "gross_margin",
            "direct_mail_margin",
        ],
        "snapshots": [
            {
                "scope_type": row.scope_type,
                "scope_id": row.scope_id,
                "metrics": row.metrics,
                "captured_at": row.captured_at,
            }
            for row in rows
        ],
    }
