from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ZEROHOUR AVIATION"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://zerohour:zerohour@localhost:5432/zerohour"
    database_replica_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    jwt_secret: str = Field(default="change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 30
    sentry_dsn: str | None = None
    stripe_secret_key: str | None = None
    stripe_annual_price_id: str | None = None
    stripe_monthly_price_id: str | None = None
    dat_api_key: str | None = None
    dat_api_secret: str | None = None
    truckstop_api_key: str | None = None
    eia_api_key: str | None = None
    openweather_api_key: str | None = None
    fred_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    flightaware_api_key: str | None = None
    flightaware_webhook_secret: str | None = None
    duffel_api_key: str | None = None
    firebase_service_account_json: str | None = None
    apple_apns_key: str | None = None
    apple_apns_key_id: str | None = None
    apple_team_id: str | None = None
    postmark_api_key: str | None = None
    postmark_from_email: str | None = None
    cloudinary_url: str | None = None
    passenger_encryption_key: str = Field(default="change-me-32-byte-passenger-key")
    cors_origins: str = "https://flyzerohour.com,http://localhost:3000,http://localhost:5173"
    sendgrid_api_key: str | None = None
    resend_api_key: str | None = None
    lob_api_key: str | None = None
    cognito_issuer: str | None = None
    cognito_audience: str | None = None
    force_cached_mode: bool = False
    provider_mode: str = "mock"
    simulated_signal_count: int = 12
    stripe_webhook_tolerance_seconds: int = 300
    owner_resolution_mode: str = "mock"
    batchdata_api_key: str | None = None
    batchdata_base_url: str = "https://api.batchdata.com"
    batchdata_owner_lookup_path: str = "/api/v1/property/owner"
    owner_resolution_session_ttl_seconds: int = 1800
    owner_resolution_daily_limit: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
