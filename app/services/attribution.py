from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CreatorSource, Referral, Tenant, User
from app.services.audit import write_audit_log


def record_creator_referral(
    db: Session,
    *,
    creator_code: str | None,
    user: User,
    tenant: Tenant,
) -> Referral | None:
    if not creator_code:
        return None
    normalized_code = creator_code.strip().lower()
    if not normalized_code:
        return None

    creator = db.query(CreatorSource).filter(CreatorSource.creator_code == normalized_code).one_or_none()
    if creator is None:
        creator = CreatorSource(
            creator_code=normalized_code,
            display_name=normalized_code,
            status="pending_review",
            commission_rules={"mode": "quality_gated"},
        )
        db.add(creator)
        db.flush()

    referral = Referral(
        creator_source_id=creator.id,
        user_id=user.id,
        tenant_id=tenant.id,
        attribution_payload={"creator_code": normalized_code, "quality_tracking": True},
    )
    db.add(referral)
    write_audit_log(
        db,
        "creator.referral_recorded",
        actor_user_id=user.id,
        entity_type="creator_source",
        entity_id=str(creator.id),
        metadata={"creator_code": normalized_code, "tenant_id": str(tenant.id)},
    )
    return referral

