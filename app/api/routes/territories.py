from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.db.session import get_db
from app.models import Territory
from app.schemas.common import StatusResponse
from app.services.provisioning import normalize_zip_codes
from app.tasks.ingestion import ingest_market, regenerate_zip_cache

router = APIRouter(prefix="/territories", tags=["territories"])


@router.get("")
def list_territories(
    db: Session = Depends(get_db), ctx: RequestContext = Depends(get_request_context)
) -> dict:
    rows = db.query(Territory).filter(Territory.tenant_id == ctx.tenant_id).all()
    return {"territories": [{"zip_code": row.zip_code, "status": row.status} for row in rows]}


@router.post("/{zip_code}", response_model=StatusResponse)
def add_territory(
    zip_code: str,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> StatusResponse:
    normalized = normalize_zip_codes([zip_code])
    if not normalized:
        return StatusResponse(status="rejected", message="Invalid ZIP code")
    existing = (
        db.query(Territory)
        .filter(Territory.tenant_id == ctx.tenant_id, Territory.zip_code == normalized[0])
        .one_or_none()
    )
    if not existing:
        db.add(Territory(tenant_id=ctx.tenant_id, zip_code=normalized[0]))
        db.commit()
    ingest_market.apply_async(args=[normalized[0], "mock"], queue="ingestion")
    regenerate_zip_cache.apply_async(args=[normalized[0]], queue="cache")
    return StatusResponse(status="queued", message="Territory added; cached intelligence is loading.")
