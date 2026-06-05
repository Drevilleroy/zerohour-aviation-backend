from __future__ import annotations

from uuid import UUID

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models import DirectMailCampaign, Letter
from app.services.audit import write_audit_log
from app.services.owner_resolution import fallback_letter_context, get_cached_letter_context
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def submit_direct_mail_campaign(self, campaign_id: str) -> dict:
    db = SessionLocal()
    try:
        campaign = db.get(DirectMailCampaign, UUID(campaign_id))
        if not campaign:
            return {"status": "missing"}
        if campaign.status in {"submitted", "completed"}:
            return {"status": "already_submitted"}

        letters = db.query(Letter).filter(Letter.campaign_id == campaign.id).all()
        property_address = campaign.metadata_.get("property_address")
        zip_code = campaign.metadata_.get("zip")
        transient_letter_context = None
        if property_address and zip_code:
            transient_letter_context = get_cached_letter_context(
                user_id=campaign.user_id,
                address=property_address,
                zip_code=zip_code,
            ) or fallback_letter_context(address=property_address, zip_code=zip_code)
        for letter in letters:
            letter.status = "submitted"
            letter.provider_payload = {
                **letter.provider_payload,
                "provider": "lob",
                "mode": "provider_submission_pending",
                "delivery_mode": "mailing_address_from_session"
                if transient_letter_context and transient_letter_context.get("resolved")
                else "property_address_fallback",
                "salutation_mode": "owner_last_name_from_session"
                if transient_letter_context and transient_letter_context.get("resolved")
                else "homeowner_fallback",
            }
        campaign.status = "submitted"
        write_audit_log(
            db,
            "direct_mail.campaign_submitted",
            actor_user_id=campaign.user_id,
            entity_type="direct_mail_campaign",
            entity_id=str(campaign.id),
            metadata={"letter_count": len(letters)},
        )
        db.commit()
        return {"status": "submitted", "campaign_id": campaign_id, "letter_count": len(letters)}
    except Exception:
        db.rollback()
        logger.exception("direct_mail_submit_failed", extra={"campaign_id": campaign_id})
        raise
    finally:
        db.close()
