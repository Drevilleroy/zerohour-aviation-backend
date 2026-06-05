from __future__ import annotations

from datetime import datetime, timedelta

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models import DailyDigest, TenantMembership, Territory
from app.services.cache import get_zip_signal_payload
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task
def generate_daily_digests() -> dict:
    db = SessionLocal()
    queued = 0
    try:
        memberships = db.query(TenantMembership).limit(10000).all()
        for membership in memberships:
            territories = db.query(Territory).filter(Territory.tenant_id == membership.tenant_id).all()
            if not territories:
                continue
            zip_payloads = []
            for territory in territories[:10]:
                _, payload = get_zip_signal_payload(db, territory.zip_code)
                zip_payloads.append(payload)
            digest = DailyDigest(
                tenant_id=membership.tenant_id,
                user_id=membership.user_id,
                status="queued",
                payload={"zips": zip_payloads},
                scheduled_for=datetime.utcnow() + timedelta(hours=1),
            )
            db.add(digest)
            db.flush()
            send_digest_email.apply_async(args=[str(membership.user_id), str(digest.id)], queue="notifications")
            queued += 1
        db.commit()
        return {"status": "queued", "digest_count": queued}
    except Exception:
        db.rollback()
        logger.exception("generate_daily_digests_failed")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_digest_email(self, user_id: str, digest_id: str) -> dict:
    return {"status": "queued_provider_send", "user_id": user_id, "digest_id": digest_id}
