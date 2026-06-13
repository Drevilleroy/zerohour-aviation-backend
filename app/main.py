from __future__ import annotations

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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

configure_logging()

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Cache-first real estate signal intelligence backend.",
)


class HTTPSOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if settings.environment == "production" and request.url.scheme != "https":
            forwarded_proto = request.headers.get("x-forwarded-proto")
            if forwarded_proto != "https":
                return JSONResponse({"detail": "HTTPS required"}, status_code=400)
        return await call_next(request)


app.add_middleware(HTTPSOnlyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(aviation.router)
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
