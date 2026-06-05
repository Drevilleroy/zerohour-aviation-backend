from __future__ import annotations

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models import BillingEvent
from app.services.billing import sync_subscription_from_stripe_event
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def reconcile_stripe_event(self, stripe_event_id: str) -> dict:
    db = SessionLocal()
    try:
        event = db.query(BillingEvent).filter(BillingEvent.stripe_event_id == stripe_event_id).one_or_none()
        if not event:
            return {"status": "missing"}

        subscription = sync_subscription_from_stripe_event(db, event)
        db.commit()
        return {
            "status": "reconciled",
            "event_id": stripe_event_id,
            "subscription_synced": subscription is not None,
        }
    except Exception:
        db.rollback()
        logger.exception("stripe_reconciliation_failed", extra={"stripe_event_id": stripe_event_id})
        raise
    finally:
        db.close()
