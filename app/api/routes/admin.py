from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import RequestContext, require_admin
from app.db.session import get_db
from app.models import FeatureFlag, IngestionRun, KillSwitch, MarketHealthScore, ProvisioningJob
from app.services.cache import redis_client
from app.tasks.ingestion import ingest_market

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/queues")
def queue_overview(ctx: RequestContext = Depends(require_admin)) -> dict:
    queue_names = [
        "provisioning",
        "ingestion",
        "normalization",
        "scoring",
        "cache",
        "notifications",
        "direct_mail",
        "billing",
        "analytics",
        "admin",
    ]
    depths = {}
    for queue_name in queue_names:
        try:
            depths[queue_name] = redis_client.llen(queue_name)
        except Exception:
            depths[queue_name] = None
    return {
        "mode": "redis_celery",
        "queues": [{"name": name, "depth": depths[name]} for name in queue_names],
        "note": "Depth is Redis LLEN for local MVP. Production should add Celery inspect/Flower/Datadog.",
    }


@router.get("/provisioning")
def provisioning_visibility(
    db: Session = Depends(get_db), ctx: RequestContext = Depends(require_admin)
) -> dict:
    rows = db.query(ProvisioningJob.status, ProvisioningJob.id).limit(100).all()
    return {"jobs": [{"id": row.id, "status": row.status} for row in rows]}


@router.get("/market-health")
def market_health(db: Session = Depends(get_db), ctx: RequestContext = Depends(require_admin)) -> dict:
    rows = db.query(MarketHealthScore).order_by(MarketHealthScore.updated_at.desc()).limit(100).all()
    return {
        "markets": [
            {
                "zip_code": row.zip_code,
                "score": float(row.score),
                "signal_density": float(row.signal_density),
                "freshness_score": float(row.freshness_score),
                "provider_health": row.provider_health,
            }
            for row in rows
        ]
    }


@router.get("/ingestion-runs")
def ingestion_runs(db: Session = Depends(get_db), ctx: RequestContext = Depends(require_admin)) -> dict:
    rows = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(100).all()
    return {
        "runs": [
            {
                "id": row.id,
                "zip_code": row.zip_code,
                "status": row.status,
                "records_seen": row.records_seen,
                "records_normalized": row.records_normalized,
                "error": row.error,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
            }
            for row in rows
        ]
    }


@router.post("/ingestion/{zip_code}/enqueue")
def enqueue_ingestion(
    zip_code: str,
    source: str = "mock",
    ctx: RequestContext = Depends(require_admin),
) -> dict:
    task = ingest_market.apply_async(args=[zip_code, source], queue="ingestion")
    return {"status": "queued", "task_id": task.id, "zip_code": zip_code, "source": source}


@router.put("/kill-switches/{key}")
def set_kill_switch(
    key: str,
    enabled: bool,
    reason: str | None = None,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require_admin),
) -> dict:
    switch = db.get(KillSwitch, key) or KillSwitch(key=key)
    switch.enabled = enabled
    switch.reason = reason
    db.merge(switch)
    db.commit()
    return {"key": key, "enabled": enabled, "reason": reason}


@router.put("/feature-flags/{key}")
def set_feature_flag(
    key: str,
    enabled: bool,
    description: str | None = None,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(require_admin),
) -> dict:
    flag = db.get(FeatureFlag, key) or FeatureFlag(key=key)
    flag.enabled = enabled
    flag.description = description
    db.merge(flag)
    db.commit()
    return {"key": key, "enabled": enabled}
