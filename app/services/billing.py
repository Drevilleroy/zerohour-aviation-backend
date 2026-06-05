from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import BillingEvent, Subscription
from app.services.audit import write_audit_log
from app.services.cache import CacheKeys, set_json

PLANS = {
    "flexible": {"interval": "month", "territory_limit": 1, "monthly_equivalent_cents": 0},
    "quarterly": {"interval": "quarter", "territory_limit": 3, "monthly_equivalent_cents": 9900},
    "annual": {"interval": "year", "territory_limit": 5, "monthly_equivalent_cents": 7900},
    "elite_annual": {"interval": "year", "territory_limit": 15, "monthly_equivalent_cents": 19900},
}


def persist_stripe_event(db: Session, *, event_id: str, event_type: str, payload: dict) -> tuple[BillingEvent, bool]:
    existing = db.query(BillingEvent).filter(BillingEvent.stripe_event_id == event_id).one_or_none()
    if existing:
        return existing, False

    event = BillingEvent(
        stripe_event_id=event_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    write_audit_log(
        db,
        "billing.webhook_received",
        entity_type="stripe_event",
        entity_id=event_id,
        metadata={"event_type": event_type},
    )
    return event, True


def sync_subscription_from_stripe_event(db: Session, event: BillingEvent) -> Subscription | None:
    event_payload = event.payload
    data_object = event_payload.get("data", {}).get("object", {})
    metadata = data_object.get("metadata") or {}
    tenant_id_value = metadata.get("tenant_id")
    if not tenant_id_value:
        return None

    tenant_id = UUID(str(tenant_id_value))
    stripe_subscription_id = data_object.get("subscription") or data_object.get("id")
    stripe_customer_id = data_object.get("customer")
    plan_key = metadata.get("plan_key") or _infer_plan_key(data_object)
    plan = PLANS.get(plan_key, PLANS["quarterly"])
    status = data_object.get("status") or _status_from_event_type(event.event_type)
    current_period_end = _timestamp_to_datetime(data_object.get("current_period_end"))

    subscription = None
    if stripe_subscription_id:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .one_or_none()
        )
    if subscription is None:
        subscription = Subscription(
            tenant_id=tenant_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            plan_key=plan_key,
            status=status,
            territory_limit=plan["territory_limit"],
            current_period_end=current_period_end,
        )
    else:
        subscription.stripe_customer_id = stripe_customer_id or subscription.stripe_customer_id
        subscription.plan_key = plan_key
        subscription.status = status
        subscription.territory_limit = plan["territory_limit"]
        subscription.current_period_end = current_period_end or subscription.current_period_end

    db.add(subscription)
    event.tenant_id = tenant_id
    event.processed_at = datetime.utcnow()
    set_json(
        CacheKeys.tenant_entitlements(str(tenant_id)),
        {
            "tenant_id": str(tenant_id),
            "plan_key": plan_key,
            "status": status,
            "territory_limit": plan["territory_limit"],
            "features": _features_for_plan(plan_key),
        },
        ttl_seconds=900,
    )
    write_audit_log(
        db,
        "billing.subscription_synced",
        entity_type="subscription",
        entity_id=str(stripe_subscription_id),
        metadata={"tenant_id": str(tenant_id), "plan_key": plan_key, "status": status},
    )
    return subscription


def _infer_plan_key(data_object: dict) -> str:
    lookup_key = data_object.get("lookup_key") or data_object.get("client_reference_id")
    if lookup_key in PLANS:
        return lookup_key
    return "quarterly"


def _status_from_event_type(event_type: str) -> str:
    if event_type.endswith(".deleted"):
        return "canceled"
    if event_type == "checkout.session.completed":
        return "active"
    return "active"


def _timestamp_to_datetime(value: int | str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.utcfromtimestamp(int(value))


def _features_for_plan(plan_key: str) -> dict:
    return {
        "direct_mail": plan_key in {"annual", "elite_annual"},
        "elite_features": plan_key == "elite_annual",
        "creator_attribution": True,
    }
