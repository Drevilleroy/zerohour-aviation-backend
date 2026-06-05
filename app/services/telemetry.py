from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import BehavioralEvent, SignalOutcome
from app.services.audit import write_audit_log


def capture_behavioral_event(
    db: Session,
    *,
    event_type: str,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    properties: dict | None = None,
) -> BehavioralEvent:
    event = BehavioralEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        properties=properties or {},
    )
    db.add(event)
    write_audit_log(
        db,
        f"behavior.{event_type}",
        actor_user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=properties or {},
    )
    return event


def capture_signal_outcome(
    db: Session,
    *,
    signal_id: UUID,
    tenant_id: UUID,
    outcome_type: str,
    properties: dict | None = None,
) -> SignalOutcome:
    outcome = SignalOutcome(
        signal_id=signal_id,
        tenant_id=tenant_id,
        outcome_type=outcome_type,
        properties=properties or {},
    )
    db.add(outcome)
    write_audit_log(
        db,
        f"signal.outcome.{outcome_type}",
        entity_type="signal",
        entity_id=str(signal_id),
        metadata={"tenant_id": str(tenant_id), **(properties or {})},
    )
    return outcome

