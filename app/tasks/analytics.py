from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from celery.utils.log import get_task_logger
from sqlalchemy import func

from app.db.session import SessionLocal
from app.models import BehavioralEvent, RetentionScore, Tenant, Territory
from app.tasks.ingestion import update_market_health
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task
def refresh_market_health() -> dict:
    db = SessionLocal()
    try:
        zip_rows = db.query(Territory.zip_code).distinct().limit(5000).all()
        for (zip_code,) in zip_rows:
            update_market_health.apply_async(args=[zip_code], queue="analytics")
        return {"status": "queued", "zip_count": len(zip_rows)}
    finally:
        db.close()


@celery_app.task
def compute_retention_risk() -> dict:
    db = SessionLocal()
    updated = 0
    try:
        tenants = db.query(Tenant).limit(10000).all()
        cutoff = datetime.utcnow() - timedelta(days=5)
        for tenant in tenants:
            recent_events = (
                db.query(func.count(BehavioralEvent.id))
                .filter(BehavioralEvent.tenant_id == tenant.id, BehavioralEvent.created_at >= cutoff)
                .scalar()
            )
            territory_count = db.query(func.count(Territory.id)).filter(Territory.tenant_id == tenant.id).scalar()
            risk_points = 0
            reasons = {}
            if not recent_events:
                risk_points += 50
                reasons["no_recent_activity"] = True
            if not territory_count:
                risk_points += 30
                reasons["no_territories"] = True
            score = max(Decimal("0"), Decimal("100") - Decimal(risk_points))
            risk_level = "high" if risk_points >= 50 else "medium" if risk_points >= 30 else "low"
            db.merge(
                RetentionScore(
                    tenant_id=tenant.id,
                    score=score,
                    risk_level=risk_level,
                    reasons=reasons,
                    updated_at=datetime.utcnow(),
                )
            )
            updated += 1
        db.commit()
        return {"status": "updated", "tenant_count": updated}
    except Exception:
        db.rollback()
        logger.exception("compute_retention_risk_failed")
        raise
    finally:
        db.close()
