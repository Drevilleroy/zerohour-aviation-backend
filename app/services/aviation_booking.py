from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import AviationBooking, AviationPassenger, AviationSignal, AviationUserProfile, DeviceToken
from app.services.aviation_pipeline import queue_proof_card
from app.services.aviation_providers import DuffelClient, NotificationClient, StripeClient
from app.services.aviation_security import decrypt_passenger_value
from app.services.cache import get_json


async def confirm_booking(db: Session, *, user_id: UUID, signal_id: UUID, offer_id: str) -> AviationBooking:
    signal = db.get(AviationSignal, signal_id)
    if not signal or signal.flight.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")

    offer = get_json(f"duffel:offer:{offer_id}")
    if not offer:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offer expired; refresh alternatives")

    profile = db.get(AviationUserProfile, user_id)
    if not profile or not profile.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Payment profile missing")

    passenger = db.query(AviationPassenger).filter(AviationPassenger.user_id == user_id).first()
    if not passenger:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passenger profile missing")

    amount = Decimal(str(offer.get("price") or "0"))
    convenience_fee = profile.plan_type == "monthly"
    if convenience_fee:
        amount += Decimal("4.99")
    amount_cents = int(amount * 100)
    stripe = StripeClient()
    payment_intent_id = await stripe.create_payment_intent(
        amount_cents=amount_cents,
        customer_id=profile.stripe_customer_id,
        idempotency_key=f"booking-{user_id}-{signal_id}",
        description=f"ZeroHour rebooking - {signal.flight.flight_number}",
        payment_method_id=profile.stripe_payment_method_id,
    )

    try:
        order = await DuffelClient().create_order(
            offer_id,
            {
                "full_name": decrypt_passenger_value(passenger.full_name) or "",
                "date_of_birth": decrypt_passenger_value(passenger.date_of_birth) or "",
                "email": passenger.email,
            },
        )
    except Exception:
        await stripe.cancel_payment_intent(payment_intent_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Booking failed; payment cancelled")

    await stripe.confirm_payment_intent(payment_intent_id, f"booking-confirm-{user_id}-{signal_id}")

    booking = AviationBooking(
        user_id=user_id,
        signal_id=signal.id,
        original_flight_id=signal.flight_id,
        new_flight_number=order["new_flight_number"],
        new_departure=_parse_datetime(order["new_departure"]),
        pnr=order["pnr"],
        duffel_order_id=order["id"],
        stripe_payment_intent_id=payment_intent_id,
        convenience_fee_charged=convenience_fee,
        amount_charged=amount,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    queue_proof_card(signal.id)

    tokens = [
        row.token
        for row in db.query(DeviceToken).filter(DeviceToken.user_id == user_id, DeviceToken.active.is_(True)).all()
    ]
    await NotificationClient().push_user(
        tokens,
        "Your new flight is confirmed",
        f"Your new flight is confirmed. {booking.new_flight_number} departs {booking.new_departure}. Confirmation: {booking.pnr}.",
        {"booking_id": str(booking.id), "signal_id": str(signal.id)},
    )
    return booking


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)
