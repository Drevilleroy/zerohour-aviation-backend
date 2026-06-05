from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.prophfesy import score_lane
from app.engine.weekly_chain import generate_weekly_chain_for_operator
from app.models import (
    BrokerScore,
    DeadZone,
    FuelAlert,
    Lane,
    Operator,
    Prediction,
    Signal,
    WeeklyLoadChain,
)
from app.schemas.freight import (
    BrokerScoreResponse,
    DeadZoneResponse,
    FuelAlertResponse,
    LanePredictionResponse,
    OperatorMcVerificationRequest,
    OperatorLaneRequest,
    OperatorResponse,
    OperatorSignupRequest,
    SignalFeedItem,
    TrackRecordItem,
    WeeklyLoadChainResponse,
)
from app.scrapers.fmcsa_scraper import McVerificationError, verify_mc_number

router = APIRouter(tags=["freight"])


@router.get("/lanes/{zip_origin}/{zip_dest}", response_model=LanePredictionResponse)
def get_lane_prediction(
    zip_origin: str,
    zip_dest: str,
    trailer_type: str = "van",
    db: Session = Depends(get_db),
) -> LanePredictionResponse:
    lane = (
        db.query(Lane)
        .filter(
            Lane.origin_zip == zip_origin,
            Lane.dest_zip == zip_dest,
            Lane.trailer_type == trailer_type,
        )
        .one_or_none()
    )
    if not lane:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not tracked")
    result = score_lane(db, lane)
    db.commit()
    db.refresh(lane)
    return _lane_response(db, lane, result.optimized_week if result else None)


@router.get("/operator/{operator_id}/dashboard", response_model=list[LanePredictionResponse])
def get_operator_dashboard(
    operator_id: UUID,
    db: Session = Depends(get_db),
) -> list[LanePredictionResponse]:
    operator = db.get(Operator, operator_id)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    lane_ids = [lane.get("lane_id") for lane in operator.top_lanes if lane.get("lane_id")]
    if not lane_ids:
        return []
    lanes = (
        db.query(Lane)
        .filter(Lane.id.in_(lane_ids))
        .order_by(desc(Lane.confidence_score))
        .all()
    )
    return [_lane_response(db, lane) for lane in lanes]


@router.get("/broker/{mc_number}/score", response_model=BrokerScoreResponse)
def get_broker_score(mc_number: str, db: Session = Depends(get_db)) -> BrokerScore:
    score = db.query(BrokerScore).filter(BrokerScore.broker_mc_number == mc_number).one_or_none()
    if not score:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker score not found")
    return score


@router.get("/fuel/{state}", response_model=FuelAlertResponse)
def get_fuel_alert(state: str, db: Session = Depends(get_db)) -> FuelAlert:
    alert = (
        db.query(FuelAlert)
        .filter(FuelAlert.state == state.upper())
        .order_by(desc(FuelAlert.created_at))
        .first()
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel alert not found")
    return alert


@router.get("/deadzones", response_model=list[DeadZoneResponse])
def list_dead_zones(db: Session = Depends(get_db)) -> list[DeadZone]:
    return (
        db.query(DeadZone)
        .filter(DeadZone.severity.in_(["HIGH", "CRITICAL"]))
        .order_by(DeadZone.severity.desc(), DeadZone.updated_at.desc())
        .all()
    )


@router.get("/track-record", response_model=list[TrackRecordItem])
def get_track_record(db: Session = Depends(get_db)) -> list[TrackRecordItem]:
    rows = (
        db.query(Prediction, Lane)
        .join(Lane, Prediction.lane_id == Lane.id)
        .order_by(desc(Prediction.created_at))
        .limit(200)
        .all()
    )
    return [
        TrackRecordItem(
            lane_id=lane.id,
            origin_zip=lane.origin_zip,
            dest_zip=lane.dest_zip,
            predicted_rate=prediction.predicted_rate,
            actual_rate=prediction.actual_rate,
            accuracy_pct=prediction.accuracy_pct,
            signal_sources=prediction.signal_sources,
            created_at=prediction.created_at,
        )
        for prediction, lane in rows
    ]


@router.post(
    "/operators/signup",
    response_model=OperatorResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup_operator(payload: OperatorSignupRequest, db: Session = Depends(get_db)) -> Operator:
    existing = db.query(Operator).filter(Operator.email == payload.email).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Operator already exists")
    carrier = _verify_mc_or_raise(payload.mc_number) if payload.mc_number else None
    home_base_zip = carrier.home_base_zip if carrier else payload.home_base_zip
    operator = Operator(
        email=str(payload.email),
        mc_number=carrier.mc_number if carrier else None,
        carrier_name=carrier.carrier_name if carrier else None,
        home_base_zip=home_base_zip,
        home_base_city=carrier.home_base_city if carrier else None,
        home_base_state=carrier.home_base_state if carrier else None,
        equipment_type=carrier.equipment_type if carrier else None,
        truck_count=payload.truck_count,
        tier=payload.tier,
        trial_start=datetime.now(timezone.utc) if carrier else None,
        subscription_status="trialing" if carrier else "pending_mc",
    )
    db.add(operator)
    db.flush()
    if carrier and home_base_zip:
        operator.top_lanes = _suggest_top_lanes(
            db,
            home_base_zip,
            carrier.home_base_state,
            carrier.equipment_type,
        )
    db.commit()
    db.refresh(operator)
    return operator


@router.post("/operators/{operator_id}/verify-mc", response_model=OperatorResponse)
def verify_operator_mc_number(
    operator_id: UUID,
    payload: OperatorMcVerificationRequest,
    db: Session = Depends(get_db),
) -> Operator:
    operator = db.get(Operator, operator_id)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    carrier = _verify_mc_or_raise(payload.mc_number)
    if not carrier.home_base_zip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MC number not found",
        )

    operator.mc_number = carrier.mc_number
    operator.carrier_name = carrier.carrier_name
    operator.home_base_zip = carrier.home_base_zip
    operator.home_base_city = carrier.home_base_city
    operator.home_base_state = carrier.home_base_state
    operator.equipment_type = carrier.equipment_type
    operator.top_lanes = _suggest_top_lanes(
        db,
        carrier.home_base_zip,
        carrier.home_base_state,
        carrier.equipment_type,
    )
    operator.trial_start = datetime.now(timezone.utc)
    operator.subscription_status = "trialing"
    db.commit()
    db.refresh(operator)
    return operator


@router.get(
    "/operators/{operator_id}/weekly-chain",
    response_model=WeeklyLoadChainResponse,
)
def get_operator_weekly_chain(
    operator_id: UUID,
    db: Session = Depends(get_db),
) -> WeeklyLoadChain:
    chain = (
        db.query(WeeklyLoadChain)
        .filter(WeeklyLoadChain.operator_id == operator_id)
        .order_by(desc(WeeklyLoadChain.created_at))
        .first()
    )
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekly chain not found")
    return chain


@router.post(
    "/operators/{operator_id}/weekly-chain",
    response_model=WeeklyLoadChainResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_operator_weekly_chain(
    operator_id: UUID,
    db: Session = Depends(get_db),
) -> WeeklyLoadChain:
    operator = db.get(Operator, operator_id)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    if not operator.home_base_zip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Home base required")
    chain = generate_weekly_chain_for_operator(db, operator)
    db.commit()
    db.refresh(chain)
    return chain


@router.post("/operators/{operator_id}/lanes", response_model=OperatorResponse)
def add_operator_lane(
    operator_id: UUID,
    payload: OperatorLaneRequest,
    db: Session = Depends(get_db),
) -> Operator:
    operator = db.get(Operator, operator_id)
    if not operator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    lane = (
        db.query(Lane)
        .filter(
            Lane.origin_zip == payload.origin_zip,
            Lane.dest_zip == payload.dest_zip,
            Lane.trailer_type == payload.trailer_type,
        )
        .one_or_none()
    )
    if not lane:
        lane = Lane(
            origin_zip=payload.origin_zip,
            dest_zip=payload.dest_zip,
            trailer_type=payload.trailer_type,
        )
        db.add(lane)
        db.flush()
    top_lanes = list(operator.top_lanes or [])
    if not any(item.get("lane_id") == str(lane.id) for item in top_lanes):
        top_lanes.append(
            {
                "lane_id": str(lane.id),
                "origin_zip": lane.origin_zip,
                "dest_zip": lane.dest_zip,
                "trailer_type": lane.trailer_type,
            }
        )
    operator.top_lanes = top_lanes
    db.commit()
    db.refresh(operator)
    return operator


@router.get("/signals/feed", response_model=list[SignalFeedItem])
def get_signal_feed(db: Session = Depends(get_db)) -> list[Signal]:
    return (
        db.query(Signal)
        .filter(Signal.lane_id.is_not(None))
        .order_by(desc(Signal.created_at))
        .limit(200)
        .all()
    )


def _verify_mc_or_raise(mc_number: str | None):
    if not mc_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MC number not found")
    try:
        return verify_mc_number(mc_number)
    except McVerificationError as exc:
        detail = "authority inactive" if "inactive" in str(exc).lower() else "MC number not found"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _suggest_top_lanes(
    db: Session,
    home_base_zip: str,
    state: str | None,
    equipment_type: str | None,
) -> list[dict]:
    trailer_type = equipment_type or "van"
    destination_zips = _destination_zips_for_state(state, home_base_zip)
    suggestions = []
    for dest_zip in destination_zips[:3]:
        lane = (
            db.query(Lane)
            .filter(
                Lane.origin_zip == home_base_zip,
                Lane.dest_zip == dest_zip,
                Lane.trailer_type == trailer_type,
            )
            .one_or_none()
        )
        if not lane:
            lane = Lane(origin_zip=home_base_zip, dest_zip=dest_zip, trailer_type=trailer_type)
            db.add(lane)
            db.flush()
        suggestions.append(
            {
                "lane_id": str(lane.id),
                "origin_zip": lane.origin_zip,
                "dest_zip": lane.dest_zip,
                "trailer_type": lane.trailer_type,
                "suggestion_reason": "home-base freight market fit",
            }
        )
    return suggestions


def _destination_zips_for_state(state: str | None, home_base_zip: str) -> list[str]:
    by_state = {
        "CA": ["75201", "85001", "98101"],
        "TX": ["90001", "30303", "60601"],
        "GA": ["33101", "75201", "60601"],
        "IL": ["30303", "75201", "07030"],
        "NJ": ["60601", "30303", "33101"],
        "NY": ["60601", "30303", "33101"],
        "WA": ["94103", "84101", "60601"],
    }
    defaults = ["75201", "30303", "60601"]
    destinations = by_state.get((state or "").upper(), defaults)
    return [dest for dest in destinations if dest != home_base_zip][:3]


def _lane_response(
    db: Session,
    lane: Lane,
    optimized_week: dict | None = None,
) -> LanePredictionResponse:
    latest_signal_output = None
    if not optimized_week:
        latest_prediction = (
            db.query(Prediction)
            .filter(Prediction.lane_id == lane.id)
            .order_by(desc(Prediction.created_at))
            .first()
        )
        if latest_prediction:
            optimized_week = latest_prediction.signal_sources.get("optimized_week")
    if optimized_week:
        latest_signal_output = {"optimized_week": optimized_week}
    return LanePredictionResponse(
        id=lane.id,
        lane_id=lane.id,
        origin_zip=lane.origin_zip,
        dest_zip=lane.dest_zip,
        trailer_type=lane.trailer_type,
        current_rate=lane.current_rate,
        predicted_rate_48hr=lane.predicted_rate_48hr,
        rate_change_pct=lane.rate_change_pct,
        confidence_score=lane.confidence_score,
        recommended_action=lane.recommended_action,
        estimated_gain=lane.estimated_gain,
        signal_count=lane.signal_count,
        last_updated=lane.last_updated,
        latest_signal_output=latest_signal_output,
    )
