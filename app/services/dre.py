from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import DreVerification, User
from app.services.audit import write_audit_log


def submit_dre_verification(
    db: Session,
    *,
    user: User,
    state: str,
    license_number: str,
) -> DreVerification:
    verification = DreVerification(
        user_id=user.id,
        state=state.upper()[:2],
        license_number=license_number.strip(),
        status="queued",
        provider_payload={"verification_mode": "async"},
    )
    db.add(verification)
    user.onboarding_state = "dre_verification_queued"
    write_audit_log(
        db,
        "dre.verification_submitted",
        actor_user_id=user.id,
        entity_type="dre_verification",
        entity_id=str(verification.id),
        metadata={"state": verification.state},
    )
    return verification

