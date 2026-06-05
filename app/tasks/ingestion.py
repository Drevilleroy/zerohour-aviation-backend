from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from celery.utils.log import get_task_logger
from sqlalchemy import desc
from sqlalchemy.dialects.postgresql import insert

from app.db.session import SessionLocal
from app.ingestion.registry import get_provider_adapter
from app.models import DataSource, IngestionRun, MarketHealthScore, Signal, ZipSignalCache
from app.services.cache import CacheKeys, set_json
from app.services.ingestion import upsert_normalized_signal
from app.services.privacy import public_signal_card
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def ingest_market(self, zip_code: str, source: str = "seed_adapter") -> dict:
    """Provider adapter entrypoint.

    Real adapters fetch provider data, normalize, dedupe, and enqueue scoring/cache jobs.
    This task intentionally stays async and is never called from dashboard request paths.
    """
    db = SessionLocal()
    try:
        adapter = get_provider_adapter(source)
        data_source = db.query(DataSource).filter(DataSource.key == adapter.source_name).one_or_none()
        if data_source is None:
            data_source = DataSource(
                key=adapter.source_name,
                source_type="simulated" if adapter.source_name == "mock_provider" else "external",
                enabled=True,
                cost_profile={"mode": "free_demo" if adapter.source_name == "mock_provider" else "provider"},
            )
            db.add(data_source)
            db.flush()

        run = IngestionRun(
            data_source_id=data_source.id,
            zip_code=zip_code,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        logger.info("ingest_market_started", extra={"zip_code": zip_code, "source": adapter.source_name})

        records = asyncio.run(adapter.fetch_zip(zip_code))
        for record in records:
            upsert_normalized_signal(db, **record.as_upsert_kwargs())
        run.status = "completed"
        run.records_seen = len(records)
        run.records_normalized = len(records)
        run.finished_at = datetime.utcnow()
        regenerate_zip_cache.apply_async(args=[zip_code], queue="cache")
        update_market_health.apply_async(args=[zip_code], queue="analytics")
        db.commit()
        return {
            "status": "ingested",
            "zip_code": zip_code,
            "source": adapter.source_name,
            "records": len(records),
        }
    except Exception as exc:
        db.rollback()
        logger.exception("ingest_market_failed", extra={"zip_code": zip_code, "source": source})
        try:
            data_source = db.query(DataSource).filter(DataSource.key == source).one_or_none()
            if data_source:
                run = IngestionRun(
                    data_source_id=data_source.id,
                    zip_code=zip_code,
                    status="failed",
                    error=str(exc),
                    started_at=datetime.utcnow(),
                    finished_at=datetime.utcnow(),
                )
                db.add(run)
                db.commit()
        finally:
            pass
        raise
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def ingest_normalized_signals(self, records: list[dict]) -> dict:
    db = SessionLocal()
    touched_zips: set[str] = set()
    try:
        for record in records:
            upsert_normalized_signal(db, **record)
            touched_zips.add(record["zip_code"])
        db.commit()
        for zip_code in touched_zips:
            regenerate_zip_cache.apply_async(args=[zip_code], queue="cache")
            update_market_health.apply_async(args=[zip_code], queue="analytics")
        return {"status": "normalized", "records": len(records), "zips": sorted(touched_zips)}
    except Exception:
        db.rollback()
        logger.exception("ingest_normalized_signals_failed")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def regenerate_zip_cache(self, zip_code: str) -> dict:
    db = SessionLocal()
    try:
        signals = (
            db.query(Signal)
            .filter(Signal.zip_code == zip_code, Signal.status == "active")
            .order_by(desc(Signal.score), desc(Signal.created_at))
            .limit(100)
            .all()
        )
        payload = {
            "zip_code": zip_code,
            "signals": [
                public_signal_card(signal)
                for signal in signals
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }
        freshness_score = Decimal("0") if not signals else sum(s.score for s in signals) / len(signals)
        stmt = insert(ZipSignalCache).values(
            zip_code=zip_code,
            version=1,
            payload=payload,
            signal_count=len(signals),
            freshness_score=freshness_score,
            generated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ZipSignalCache.zip_code, ZipSignalCache.version],
            set_={
                "payload": payload,
                "signal_count": len(signals),
                "freshness_score": freshness_score,
                "generated_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=24),
            },
        )
        db.execute(stmt)
        db.commit()
        set_json(CacheKeys.zip_signals(zip_code), payload, ttl_seconds=3600)
        return {"status": "cache_regenerated", "zip_code": zip_code, "signal_count": len(signals)}
    except Exception:
        db.rollback()
        logger.exception("regenerate_zip_cache_failed", extra={"zip_code": zip_code})
        raise
    finally:
        db.close()


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def update_market_health(self, zip_code: str) -> dict:
    db = SessionLocal()
    try:
        signal_count = db.query(Signal).filter(Signal.zip_code == zip_code).count()
        score = min(100, signal_count * 2)
        health = MarketHealthScore(
            zip_code=zip_code,
            score=Decimal(score),
            signal_density=Decimal(signal_count),
            freshness_score=Decimal(score),
            provider_health={"status": "ok" if signal_count else "low_data"},
        )
        db.merge(health)
        db.commit()
        return {"status": "market_health_updated", "zip_code": zip_code, "score": score}
    finally:
        db.close()
