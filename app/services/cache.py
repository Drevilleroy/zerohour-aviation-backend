from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ZipSignalCache

redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=settings.redis_max_connections,
    socket_timeout=settings.redis_socket_timeout_seconds,
    socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
    health_check_interval=30,
)


class CacheKeys:
    @staticmethod
    def zip_signals(zip_code: str) -> str:
        return f"zip:{zip_code}:signals:v1"

    @staticmethod
    def user_dashboard(user_id: str) -> str:
        return f"user:{user_id}:dashboard:v1"

    @staticmethod
    def feature_flags() -> str:
        return "feature_flags:v1"

    @staticmethod
    def kill_switches() -> str:
        return "kill_switches:v1"

    @staticmethod
    def tenant_entitlements(tenant_id: str) -> str:
        return f"tenant:{tenant_id}:entitlements:v1"

    @staticmethod
    def owner_resolution_session(user_id: str, address: str, zip_code: str) -> str:
        fingerprint = sha256(f"{address.strip().lower()}:{zip_code}".encode("utf-8")).hexdigest()
        return f"owner_resolution:{user_id}:{fingerprint}"

    @staticmethod
    def owner_resolution_rate_limit(user_id: str) -> str:
        return f"rate_limit:owner_resolution:{user_id}:{date.today().isoformat()}"


def get_json(key: str) -> dict[str, Any] | None:
    try:
        value = redis_client.get(key)
    except RedisError:
        return None
    if not value:
        return None
    return json.loads(value)


def set_json(key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> None:
    try:
        redis_client.set(key, json.dumps(payload, default=str), ex=ttl_seconds)
    except RedisError:
        return


def increment_daily_counter(key: str) -> int:
    value = redis_client.incr(key)
    if value == 1:
        tomorrow = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        seconds_until_tomorrow = max(int((tomorrow - datetime.now()).total_seconds()), 60)
        redis_client.expire(key, seconds_until_tomorrow)
    return int(value)


def get_zip_signal_payload(db: Session, zip_code: str) -> tuple[str, dict[str, Any]]:
    cached = get_json(CacheKeys.zip_signals(zip_code))
    if cached is not None:
        return "redis", _sanitize_zip_cache_payload(cached)

    row = (
        db.query(ZipSignalCache)
        .filter(ZipSignalCache.zip_code == zip_code, ZipSignalCache.version == 1)
        .one_or_none()
    )
    if row:
        payload = _sanitize_zip_cache_payload(row.payload | {"generated_at": row.generated_at.isoformat()})
        set_json(CacheKeys.zip_signals(zip_code), payload, ttl_seconds=900)
        return "postgres_stale_ok", payload

    return (
        "degraded_empty",
        {
            "zip_code": zip_code,
            "signals": [],
            "message": "Signal intelligence is processing for this ZIP.",
            "generated_at": datetime.utcnow().isoformat(),
        },
    )


def _sanitize_zip_cache_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    signals = []
    for signal in sanitized.get("signals", []):
        if not isinstance(signal, dict):
            continue
        item = dict(signal)
        item.pop("payload", None)
        for key in (
            "owner",
            "owner_name",
            "owner_full_name",
            "homeowner_name",
            "mailing_address",
            "owner_mailing_address",
        ):
            item.pop(key, None)
        signals.append(item)
    sanitized["signals"] = signals
    return sanitized
