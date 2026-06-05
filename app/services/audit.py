from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit_log(
    db: Session,
    action: str,
    *,
    actor_user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_=metadata or {},
        )
    )

