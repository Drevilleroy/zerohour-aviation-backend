from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.db.session import get_db
from app.models import Signal
from app.schemas.common import OutcomeRequest, SecondPlaceAlertResponse, StatusResponse
from app.schemas.owner_resolution import OwnerResolutionRequest, OwnerResolutionResponse
from app.services.owner_resolution import (
    OwnerResolutionRateLimitExceeded,
    OwnerResolutionRateLimitUnavailable,
    resolve_owner_for_user,
)
from app.services.privacy import public_signal_card
from app.services.signal_claims import claim_signal_for_user, consume_second_place_alert
from app.services.telemetry import capture_behavioral_event, capture_signal_outcome

router = APIRouter(prefix="/signals", tags=["signals"])
legacy_router = APIRouter(prefix="/signals", tags=["signals"])


def _second_place_alert(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> SecondPlaceAlertResponse:
    response = consume_second_place_alert(db, user_id=ctx.user_id)
    db.commit()
    return SecondPlaceAlertResponse(**response)


router.get("/second-place-alert", response_model=SecondPlaceAlertResponse)(_second_place_alert)
legacy_router.get("/second-place-alert", response_model=SecondPlaceAlertResponse)(_second_place_alert)


async def _resolve_owner(
    payload: OwnerResolutionRequest,
    ctx: RequestContext = Depends(get_request_context),
) -> OwnerResolutionResponse:
    try:
        result = await resolve_owner_for_user(
            user_id=ctx.user_id,
            address=payload.address,
            zip_code=payload.zip,
        )
    except OwnerResolutionRateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except OwnerResolutionRateLimitUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OwnerResolutionResponse(
        resolved=result.resolved,
        name=result.name,
        mailing_address=result.mailing_address,
    )


router.post("/resolve-owner", response_model=OwnerResolutionResponse)(_resolve_owner)
legacy_router.post("/resolve-owner", response_model=OwnerResolutionResponse)(_resolve_owner)


@router.get("")
def list_signals(
    zip_code: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    query = db.query(Signal).filter(Signal.status == "active")
    if zip_code:
        query = query.filter(Signal.zip_code == zip_code)
    rows = query.order_by(Signal.score.desc(), Signal.created_at.desc()).limit(limit).all()
    return {"signals": [public_signal_card(row) for row in rows]}


@router.post("/{signal_id}/view", response_model=StatusResponse)
def view_signal(
    signal_id: UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> StatusResponse:
    signal = db.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    capture_behavioral_event(
        db,
        event_type="signal_viewed",
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        entity_type="signal",
        entity_id=str(signal_id),
    )
    claim_delta_minutes = claim_signal_for_user(
        db,
        signal=signal,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    db.commit()
    return StatusResponse(
        status="recorded",
        message=(
            f"Signal claim timing captured at {claim_delta_minutes} minutes."
            if claim_delta_minutes is not None
            else None
        ),
    )


@router.post("/{signal_id}/claim", response_model=StatusResponse)
def claim_signal(
    signal_id: UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> StatusResponse:
    signal = db.get(Signal, signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    capture_behavioral_event(
        db,
        event_type="signal_claimed",
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        entity_type="signal",
        entity_id=str(signal_id),
    )
    claim_delta_minutes = claim_signal_for_user(
        db,
        signal=signal,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    db.commit()
    return StatusResponse(
        status="claimed",
        message=(
            f"Signal claim timing captured at {claim_delta_minutes} minutes."
            if claim_delta_minutes is not None
            else None
        ),
    )


@router.post("/{signal_id}/outcomes", response_model=StatusResponse)
def signal_outcome(
    signal_id: UUID,
    payload: OutcomeRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(get_request_context),
) -> StatusResponse:
    if not db.get(Signal, signal_id):
        raise HTTPException(status_code=404, detail="Signal not found")
    capture_signal_outcome(
        db,
        signal_id=signal_id,
        tenant_id=ctx.tenant_id,
        outcome_type=payload.outcome_type,
        properties=payload.properties,
    )
    db.commit()
    return StatusResponse(status="recorded")
