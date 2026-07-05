from __future__ import annotations

from hashlib import sha256
import uuid

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.api.routes import (
    admin,
    analytics,
    aviation,
    auth,
    billing,
    creators,
    dashboard,
    direct_mail,
    freight,
    health,
    onboarding,
    signals,
    territories,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.cache import redis_client

configure_logging()

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Flight disruption intelligence and direct-airline booking backend.",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


class AllowedHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if settings.environment != "production":
            return await call_next(request)
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        allowed_hosts = [item.strip().lower() for item in settings.allowed_hosts.split(",") if item.strip()]
        allowed = any(
            host == allowed_host
            or (allowed_host.startswith("*.") and host.endswith(allowed_host[1:]))
            for allowed_host in allowed_hosts
        )
        if not allowed:
            return JSONResponse({"detail": "Host not allowed"}, status_code=400)
        return await call_next(request)


class HTTPSOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if settings.environment == "production" and request.url.scheme != "https":
            forwarded_proto = request.headers.get("x-forwarded-proto")
            if forwarded_proto != "https":
                return JSONResponse({"detail": "HTTPS required"}, status_code=400)
        return await call_next(request)


class BackupRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.backup_rate_limit_enabled or request.url.path.startswith("/health"):
            return await call_next(request)
        if request.url.path.startswith("/webhooks/"):
            return await call_next(request)

        limit, window_seconds, scope = _rate_limit_policy(request)
        if limit <= 0:
            return await call_next(request)

        identifier = _rate_limit_identifier(request)
        window = int(request.scope.get("time_window") or 0)
        if not window:
            import time

            window = int(time.time() // window_seconds)
        key = f"rate:{scope}:{identifier}:{window}"

        try:
            count = int(redis_client.incr(key))
            if count == 1:
                redis_client.expire(key, window_seconds)
        except RedisError:
            return await call_next(request)

        if count > limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(window_seconds)},
            )
        response = await call_next(request)
        response.headers["x-ratelimit-limit"] = str(limit)
        response.headers["x-ratelimit-remaining"] = str(max(limit - count, 0))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "no-referrer")
        response.headers.setdefault("permissions-policy", "geolocation=(), microphone=(), camera=()")
        return response


def _rate_limit_policy(request: Request) -> tuple[int, int, str]:
    path = request.url.path
    if request.method == "POST" and path == "/auth/register":
        return settings.auth_register_rate_limit_per_hour, 3600, "auth_register"
    if request.method == "POST" and path == "/auth/login":
        return settings.auth_login_rate_limit_per_hour, 3600, "auth_login"
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return settings.authenticated_rate_limit_per_minute, 60, "authenticated"
    return settings.anonymous_rate_limit_per_minute, 60, "anonymous"


def _rate_limit_identifier(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return sha256(authorization.split(" ", 1)[1].encode("utf-8")).hexdigest()[:32]
    forwarded_for = request.headers.get("x-forwarded-for", "")
    ip_address = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
    if not ip_address and request.client:
        ip_address = request.client.host
    return sha256((ip_address or "unknown").encode("utf-8")).hexdigest()[:32]


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BackupRateLimitMiddleware)
app.add_middleware(HTTPSOnlyMiddleware)
app.add_middleware(AllowedHostMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(aviation.router)

if settings.environment != "production" or settings.mount_legacy_routes:
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(onboarding.router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
    app.include_router(signals.router, prefix=settings.api_v1_prefix)
    app.include_router(signals.legacy_router, prefix="/api")
    app.include_router(territories.router, prefix=settings.api_v1_prefix)
    app.include_router(billing.router, prefix=settings.api_v1_prefix)
    app.include_router(direct_mail.router, prefix=settings.api_v1_prefix)
    app.include_router(creators.router, prefix=settings.api_v1_prefix)
    app.include_router(analytics.router, prefix=settings.api_v1_prefix)
    app.include_router(admin.router, prefix=settings.api_v1_prefix)
    app.include_router(freight.router, prefix=settings.api_v1_prefix)
    app.include_router(freight.router)
