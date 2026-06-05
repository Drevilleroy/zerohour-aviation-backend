from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import SecondPlaceAlert, Signal, Subscription, TenantMembership, Territory, User
from app.services.audit import write_audit_log

PRIORITY_CLAIM_PLANS = {"quarterly", "annual", "elite_annual"}
FLEXIBLE_PLAN = "flexible"
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def calculate_claim_delta_minutes(signal_fired_at: datetime, signal_claimed_at: datetime) -> int:
    fired_at = _as_aware_utc(signal_fired_at)
    claimed_at = _as_aware_utc(signal_claimed_at)
    return int((claimed_at - fired_at).total_seconds() // 60)


def claim_signal_for_user(db: Session, *, signal: Signal, tenant_id: UUID, user_id: UUID) -> int | None:
    if signal.signal_claimed_at is not None:
        if signal.claimed_by_user_id == user_id:
            return signal.claim_delta_minutes
        return None

    if not _tenant_has_priority_claim_plan(db, tenant_id):
        write_audit_log(
            db,
            "signal.claim_recorded_without_priority_plan",
            actor_user_id=user_id,
            entity_type="signal",
            entity_id=str(signal.id),
            metadata={"tenant_id": str(tenant_id)},
        )
        return None

    claimed_at = datetime.now(timezone.utc)
    fired_at = signal.signal_fired_at or signal.created_at or claimed_at
    claim_delta_minutes = calculate_claim_delta_minutes(fired_at, claimed_at)

    signal.signal_claimed_at = claimed_at
    signal.claimed_by_user_id = user_id
    signal.claim_delta_minutes = claim_delta_minutes

    queued_count = queue_second_place_alerts_for_flexible_agents(
        db,
        signal=signal,
        claiming_user_id=user_id,
        claim_delta_minutes=claim_delta_minutes,
    )
    write_audit_log(
        db,
        "signal.claimed",
        actor_user_id=user_id,
        entity_type="signal",
        entity_id=str(signal.id),
        metadata={
            "tenant_id": str(tenant_id),
            "claim_delta_minutes": claim_delta_minutes,
            "second_place_alerts_queued": queued_count,
        },
    )
    return claim_delta_minutes


def queue_second_place_alerts_for_flexible_agents(
    db: Session,
    *,
    signal: Signal,
    claiming_user_id: UUID,
    claim_delta_minutes: int,
) -> int:
    flexible_memberships = (
        db.query(TenantMembership)
        .join(Territory, Territory.tenant_id == TenantMembership.tenant_id)
        .join(Subscription, Subscription.tenant_id == TenantMembership.tenant_id)
        .join(User, User.id == TenantMembership.user_id)
        .filter(Territory.zip_code == signal.zip_code)
        .filter(Subscription.plan_key == FLEXIBLE_PLAN)
        .filter(Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES))
        .filter(User.second_place_shown.is_(False))
        .all()
    )

    queued_count = 0
    for membership in flexible_memberships:
        if membership.user_id == claiming_user_id:
            continue
        existing_alert = (
            db.query(SecondPlaceAlert)
            .filter(SecondPlaceAlert.user_id == membership.user_id)
            .one_or_none()
        )
        if existing_alert:
            continue
        db.add(
            SecondPlaceAlert(
                user_id=membership.user_id,
                signal_id=signal.id,
                signal_type=_display_signal_type(signal.signal_type),
                address=_display_signal_address(signal),
                claim_delta_minutes=claim_delta_minutes,
            )
        )
        queued_count += 1

    return queued_count


def consume_second_place_alert(db: Session, *, user_id: UUID) -> dict:
    user = db.get(User, user_id)
    if not user or user.second_place_shown:
        return {"show": False}

    alert = (
        db.query(SecondPlaceAlert)
        .filter(SecondPlaceAlert.user_id == user_id, SecondPlaceAlert.shown_at.is_(None))
        .order_by(SecondPlaceAlert.queued_at.asc())
        .first()
    )
    if not alert:
        return {"show": False}

    alert.shown_at = datetime.now(timezone.utc)
    user.second_place_shown = True
    write_audit_log(
        db,
        "signal.second_place_alert_shown",
        actor_user_id=user_id,
        entity_type="signal",
        entity_id=str(alert.signal_id),
        metadata={"claim_delta_minutes": alert.claim_delta_minutes},
    )
    return {
        "show": True,
        "signal_type": alert.signal_type,
        "address": alert.address,
        "claim_delta_minutes": alert.claim_delta_minutes,
    }


def _tenant_has_priority_claim_plan(db: Session, tenant_id: UUID) -> bool:
    subscription = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == tenant_id)
        .filter(Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES))
        .order_by(Subscription.current_period_end.desc().nullslast())
        .first()
    )
    return bool(subscription and subscription.plan_key in PRIORITY_CLAIM_PLANS)


def _display_signal_type(signal_type: str) -> str:
    return signal_type.replace("_", " ").upper()


def _display_signal_address(signal: Signal) -> str | None:
    for key in ("address", "display_address", "property_address", "street_address"):
        value = signal.payload.get(key)
        if value:
            return str(value)
    return signal.address_hash


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
