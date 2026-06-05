from __future__ import annotations

from uuid import UUID

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models import ProvisioningJob
from app.services.cache import CacheKeys, set_json
from app.services.dashboard import build_dashboard_snapshot
from app.services.provisioning import apply_provisioning_job
from app.tasks.ingestion import ingest_market, regenerate_zip_cache
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def process_provisioning_job(self, job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = db.get(ProvisioningJob, UUID(job_id))
        if not job:
            return {"status": "missing"}
        if job.status == "ready":
            return {"status": "already_ready"}

        apply_provisioning_job(db, job)
        db.commit()

        zip_codes = job.requested_zips.get("zip_codes", [])
        for zip_code in zip_codes:
            ingest_market.apply_async(args=[zip_code, "mock"], queue="ingestion")
            regenerate_zip_cache.apply_async(args=[zip_code], queue="cache")

        dashboard_payload = build_dashboard_snapshot(db, tenant_id=job.tenant_id, user_id=job.user_id)
        dashboard_payload["mode"] = "provisioning_complete"
        dashboard_payload["message"] = "Dashboard ready. ZIP intelligence is loading from cache as available."
        set_json(CacheKeys.user_dashboard(str(job.user_id)), dashboard_payload, ttl_seconds=900)
        return {"status": "ready", "zip_count": len(zip_codes)}
    except Exception:
        db.rollback()
        logger.exception("provisioning_job_failed", extra={"job_id": job_id})
        raise
    finally:
        db.close()
