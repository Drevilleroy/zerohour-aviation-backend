from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.cache import redis_client

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    db_ok = True
    redis_ok = True
    try:
        db.execute(text("select 1"))
    except Exception:
        db_ok = False
    try:
        redis_client.ping()
    except RedisError:
        redis_ok = False
    degraded = settings.force_cached_mode or not db_ok or not redis_ok
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "degraded" if degraded else "ok",
        "database": "ok" if db_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
        "queue": "ok" if redis_ok else "unavailable",
        "force_cached_mode": settings.force_cached_mode,
    }


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    response = Response()
    status = health(response, db)
    if status["database"] != "ok":
        return {**status, "status": "not_ready"}
    return {**status, "status": "ready"}
