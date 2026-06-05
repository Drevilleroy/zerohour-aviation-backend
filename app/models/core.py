from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    tenant_type: Mapped[str] = mapped_column(String(50), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    auth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    onboarding_state: Mapped[str] = mapped_column(String(50), default="created")
    second_place_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(50), default="owner")
    tenant: Mapped[Tenant] = relationship()
    user: Mapped[User] = relationship()


class Territory(Base):
    __tablename__ = "territories"
    __table_args__ = (UniqueConstraint("tenant_id", "zip_code", name="uq_tenant_zip"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    zip_code: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProvisioningJob(Base):
    __tablename__ = "provisioning_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    requested_zips: Mapped[dict] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("source", "subject_hash", "signal_type", name="uq_signal_dedupe"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    lane_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lanes.id"), index=True)
    zip_code: Mapped[str] = mapped_column(String(10), index=True)
    signal_type: Mapped[str] = mapped_column(String(80), index=True)
    signal_value: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(20), default="NEUTRAL", index=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    subject_hash: Mapped[str] = mapped_column(String(128))
    address_hash: Mapped[str | None] = mapped_column(String(128))
    event_date: Mapped[date | None] = mapped_column(Date)
    freshness_days: Mapped[int] = mapped_column(default=0)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    status: Mapped[str] = mapped_column(String(50), default="active")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    signal_fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    signal_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    claim_delta_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ZipSignalCache(Base):
    __tablename__ = "zip_signal_caches"

    zip_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True, default=1)
    payload: Mapped[dict] = mapped_column(JSONB)
    signal_count: Mapped[int] = mapped_column(default=0)
    freshness_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BehavioralEvent(Base):
    __tablename__ = "behavioral_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(120))
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id: Mapped[uuid.UUID] = uuid_pk()
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    outcome_type: Mapped[str] = mapped_column(String(80), index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecondPlaceAlert(Base):
    __tablename__ = "second_place_alerts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_second_place_alert_user_once"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(255))
    claim_delta_minutes: Mapped[int] = mapped_column(Integer)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)


class KillSwitch(Base):
    __tablename__ = "kill_switches"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketHealthScore(Base):
    __tablename__ = "market_health_scores"

    zip_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    signal_density: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    freshness_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    provider_health: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(120))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DreVerification(Base):
    __tablename__ = "dre_verifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(String(2))
    license_number: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    provider_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    plan_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="incomplete")
    territory_limit: Mapped[int] = mapped_column(default=0)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    stripe_event_id: Mapped[str] = mapped_column(String(160), unique=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(120), unique=True)
    source_type: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(default=True)
    cost_profile: Mapped[dict] = mapped_column(JSONB, default=dict)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), index=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    records_seen: Mapped[int] = mapped_column(default=0)
    records_normalized: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawRecord(Base):
    __tablename__ = "raw_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_record_hash: Mapped[str] = mapped_column(String(128), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DirectMailCampaign(Base):
    __tablename__ = "direct_mail_campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    credit_cost: Mapped[int] = mapped_column(default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Letter(Base):
    __tablename__ = "letters"

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("direct_mail_campaigns.id"), index=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"))
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    lob_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    provider_payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class MailSuppression(Base):
    __tablename__ = "mail_suppressions"

    id: Mapped[uuid.UUID] = uuid_pk()
    address_hash: Mapped[str] = mapped_column(String(128), unique=True)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreatorSource(Base):
    __tablename__ = "creator_sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    creator_code: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")
    commission_rules: Mapped[dict] = mapped_column(JSONB, default=dict)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = uuid_pk()
    creator_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("creator_sources.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    attribution_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetentionScore(Base):
    __tablename__ = "retention_scores"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    risk_level: Mapped[str] = mapped_column(String(50), default="unknown")
    reasons: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AbuseFlag(Base):
    __tablename__ = "abuse_flags"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(30), default="medium")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DisclaimerAcceptance(Base):
    __tablename__ = "disclaimer_acceptances"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    disclaimer_key: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnitEconomicsSnapshot(Base):
    __tablename__ = "unit_economics_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    scope_type: Mapped[str] = mapped_column(String(50), index=True)
    scope_id: Mapped[str] = mapped_column(String(120), index=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
