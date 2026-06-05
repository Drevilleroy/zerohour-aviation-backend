from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, get_request_context
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.db.session import get_db, get_read_db
from app.models import (
    AviationBooking,
    AviationFlight,
    AviationPassenger,
    AviationSignal,
    AviationUserProfile,
    DeviceToken,
    SignupQueueItem,
    Tenant,
    TenantMembership,
    User,
)
from app.schemas.aviation import (
    BookingConfirmRequest,
    BookingResponse,
    DeviceRegisterRequest,
    FlightCreateRequest,
    FlightResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    SignalResponse,
    TokenResponse,
)
from app.services.aviation_booking import confirm_booking
from app.services.aviation_pipeline import enqueue_flightaware_webhook, process_flightaware_payload
from app.services.aviation_providers import FlightAwareClient, PostmarkClient, StripeClient
from app.services.aviation_security import encrypt_passenger_value, verify_hmac_sha256
from app.services.cache import redis_client
from app.services.stripe import StripeSignatureError, verify_stripe_signature

router = APIRouter(tags=["aviation"])


@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    item = SignupQueueItem(email=payload.email.lower(), payload=payload.model_dump(mode="json"))
    db.add(item)
    db.commit()
    db.refresh(item)
    redis_client.lpush("queue:signup", json.dumps({"signup_queue_id": str(item.id)}))
    return RegisterResponse(
        status="queued",
        message="Account creation is queued and should be active within 60 seconds.",
        signup_queue_id=item.id,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest) -> TokenResponse:
    try:
        decoded = jwt.decode(payload.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if decoded.get("token_type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    token = create_access_token(uuid.UUID(decoded["sub"]), uuid.UUID(decoded["tenant_id"]), decoded.get("role", "member"))
    return TokenResponse(access_token=token)


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).one_or_none()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    membership = db.query(TenantMembership).filter(TenantMembership.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant membership")
    return LoginResponse(
        access_token=create_access_token(user.id, membership.tenant_id, membership.role),
        refresh_token=create_refresh_token(user.id, membership.tenant_id, membership.role),
    )


async def process_signup_queue_item(db: Session, item_id: uuid.UUID) -> User:
    item = db.get(SignupQueueItem, item_id)
    if not item:
        raise ValueError("Signup queue item not found")
    payload = RegisterRequest.model_validate(item.payload)
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.name,
        onboarding_state="active",
    )
    tenant = Tenant(name=payload.name or payload.email, tenant_type="aviation")
    db.add_all([user, tenant])
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="owner"))
    customer_id = await StripeClient().create_customer(payload.email, payload.name)
    amount_cents = 7900 if payload.plan_type == "annual" else 999
    await StripeClient().create_payment_intent(
        amount_cents=amount_cents,
        customer_id=customer_id,
        idempotency_key=f"signup-{user.id}-{payload.plan_type}",
        description=f"ZeroHour Aviation {payload.plan_type} subscription",
        payment_method_id=payload.payment_method_id,
    )
    db.add(
        AviationUserProfile(
            user_id=user.id,
            stripe_customer_id=customer_id,
            stripe_payment_method_id=payload.payment_method_id,
            plan_type=payload.plan_type,
            referring_creator_id=payload.referring_creator_id,
            active=True,
        )
    )
    if payload.passenger_full_name and payload.passenger_date_of_birth:
        db.add(
            AviationPassenger(
                user_id=user.id,
                full_name=encrypt_passenger_value(payload.passenger_full_name),
                date_of_birth=encrypt_passenger_value(payload.passenger_date_of_birth),
                email=payload.email,
            )
        )
    item.status = "processed"
    item.processed_at = datetime.now(UTC)
    db.commit()
    await PostmarkClient().send_email(payload.email, "Welcome to ZeroHour Aviation", "Your account is active.")
    return user


@router.post("/flights", response_model=FlightResponse, status_code=status.HTTP_201_CREATED)
async def add_flight(
    payload: FlightCreateRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> AviationFlight:
    webhook_id = await FlightAwareClient().register_webhook(payload.flight_number, payload.departure_date)
    flight = AviationFlight(
        user_id=ctx.user_id,
        flight_number=payload.flight_number.upper(),
        departure_date=payload.departure_date,
        scheduled_arrival_time=payload.scheduled_arrival_time,
        origin=payload.origin.upper(),
        destination=payload.destination.upper(),
        cabin_class=payload.cabin_class,
        flightaware_webhook_id=webhook_id,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


@router.get("/flights", response_model=list[FlightResponse])
def list_flights(
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_read_db),
) -> list[AviationFlight]:
    return db.query(AviationFlight).filter(AviationFlight.user_id == ctx.user_id).order_by(AviationFlight.created_at.desc()).all()


@router.delete("/flights/{flight_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flight(
    flight_id: uuid.UUID,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> Response:
    flight = db.get(AviationFlight, flight_id)
    if not flight or flight.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")
    flight.status = "stopped"
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/signals", response_model=list[SignalResponse])
def list_signals(ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_read_db)) -> list[AviationSignal]:
    return (
        db.query(AviationSignal)
        .join(AviationFlight, AviationSignal.flight_id == AviationFlight.id)
        .filter(AviationFlight.user_id == ctx.user_id)
        .order_by(AviationSignal.fired_at.desc())
        .all()
    )


@router.get("/signals/{signal_id}", response_model=SignalResponse)
def get_signal(signal_id: uuid.UUID, ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_read_db)) -> AviationSignal:
    signal = db.get(AviationSignal, signal_id)
    if not signal or signal.flight.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    return signal


@router.post("/bookings/confirm", response_model=BookingResponse)
async def create_booking(
    payload: BookingConfirmRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> BookingResponse:
    booking = await confirm_booking(db, user_id=ctx.user_id, signal_id=payload.signal_id, offer_id=payload.offer_id)
    return BookingResponse(
        id=booking.id,
        signal_id=booking.signal_id,
        new_flight_number=booking.new_flight_number,
        new_departure=booking.new_departure,
        pnr=booking.pnr,
        duffel_order_id=booking.duffel_order_id,
        stripe_payment_intent_id=booking.stripe_payment_intent_id,
        convenience_fee_charged=booking.convenience_fee_charged,
        amount_charged=float(booking.amount_charged),
    )


@router.get("/bookings", response_model=list[BookingResponse])
def list_bookings(ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_read_db)) -> list[BookingResponse]:
    rows = db.query(AviationBooking).filter(AviationBooking.user_id == ctx.user_id).order_by(AviationBooking.created_at.desc()).all()
    return [
        BookingResponse(
            id=row.id,
            signal_id=row.signal_id,
            new_flight_number=row.new_flight_number,
            new_departure=row.new_departure,
            pnr=row.pnr,
            duffel_order_id=row.duffel_order_id,
            stripe_payment_intent_id=row.stripe_payment_intent_id,
            convenience_fee_charged=row.convenience_fee_charged,
            amount_charged=float(row.amount_charged),
        )
        for row in rows
    ]


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: uuid.UUID, ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_read_db)) -> BookingResponse:
    row = db.get(AviationBooking, booking_id)
    if not row or row.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return BookingResponse(
        id=row.id,
        signal_id=row.signal_id,
        new_flight_number=row.new_flight_number,
        new_departure=row.new_departure,
        pnr=row.pnr,
        duffel_order_id=row.duffel_order_id,
        stripe_payment_intent_id=row.stripe_payment_intent_id,
        convenience_fee_charged=row.convenience_fee_charged,
        amount_charged=float(row.amount_charged),
    )


@router.get("/proof-cards/{signal_id}")
def get_proof_card(signal_id: uuid.UUID, ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_read_db)) -> dict:
    signal = db.get(AviationSignal, signal_id)
    if not signal or signal.flight.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    return {"signal_id": signal.id, "proof_card_url": signal.proof_card_url, "confirmed": signal.confirmed}


@router.post("/devices/register", status_code=status.HTTP_204_NO_CONTENT)
def register_device(
    payload: DeviceRegisterRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> Response:
    existing = db.query(DeviceToken).filter(DeviceToken.user_id == ctx.user_id, DeviceToken.token == payload.token).first()
    if existing:
        existing.active = True
        existing.platform = payload.platform
    else:
        db.add(DeviceToken(user_id=ctx.user_id, token=payload.token, platform=payload.platform))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(token: str, ctx: RequestContext = Depends(get_request_context), db: Session = Depends(get_db)) -> Response:
    row = db.query(DeviceToken).filter(DeviceToken.user_id == ctx.user_id, DeviceToken.token == token).first()
    if row:
        row.active = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/webhooks/flightaware", status_code=status.HTTP_200_OK)
async def flightaware_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-FlightAware-Signature"),
) -> dict:
    raw = await request.body()
    if not verify_hmac_sha256(raw, signature, settings.flightaware_webhook_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid FlightAware signature")
    payload = json.loads(raw.decode("utf-8"))
    enqueue_flightaware_webhook(payload)
    if settings.environment == "local":
        await process_flightaware_payload(db, payload)
    return {"status": "queued"}


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, signature: str | None = Header(default=None, alias="Stripe-Signature")) -> dict:
    raw = await request.body()
    try:
        verify_stripe_signature(
            payload=raw,
            signature_header=signature,
            webhook_secret=settings.stripe_webhook_secret,
            tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
        )
    except StripeSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Stripe signature") from exc
    return {"status": "received"}
