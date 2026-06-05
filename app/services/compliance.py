from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import AbuseFlag, DirectMailCampaign, MailSuppression
from app.services.feature_flags import is_feature_enabled, is_kill_switch_enabled


class ComplianceError(Exception):
    pass


def enforce_direct_mail_controls(
    db: Session,
    *,
    tenant_id,
    recipient_address_hashes: list[str],
) -> None:
    if is_kill_switch_enabled(db, "pause_direct_mail") or not is_feature_enabled(
        db, "direct_mail", default=False
    ):
        raise ComplianceError("Direct mail is currently unavailable.")

    if not recipient_address_hashes:
        raise ComplianceError("At least one recipient is required.")

    suppressed = (
        db.query(MailSuppression.address_hash)
        .filter(MailSuppression.address_hash.in_(recipient_address_hashes))
        .limit(1)
        .first()
    )
    if suppressed:
        raise ComplianceError("One or more recipients are suppressed.")

    recent_count = (
        db.query(DirectMailCampaign)
        .filter(
            DirectMailCampaign.tenant_id == tenant_id,
            DirectMailCampaign.created_at >= datetime.utcnow() - timedelta(days=1),
        )
        .count()
    )
    if recent_count >= 25:
        db.add(
            AbuseFlag(
                tenant_id=tenant_id,
                flag_type="direct_mail_velocity",
                severity="high",
                metadata_={"campaigns_last_24h": recent_count},
            )
        )
        raise ComplianceError("Direct mail daily fair-use limit reached.")

