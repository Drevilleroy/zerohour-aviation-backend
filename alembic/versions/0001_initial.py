from __future__ import annotations

"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tenant_type", sa.String(50), nullable=False, server_default="agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("auth_subject", sa.String(255), nullable=True, unique=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("onboarding_state", sa.String(50), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="owner"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),
    )
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "kill_switches",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "territories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("zip_code", sa.String(10), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "zip_code", name="uq_tenant_zip"),
    )
    op.create_index("ix_territories_zip_code", "territories", ["zip_code"])
    op.create_table(
        "provisioning_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("requested_zips", postgresql.JSONB(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_provisioning_status_created", "provisioning_jobs", ["status", "created_at"])
    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("zip_code", sa.String(10), nullable=False),
        sa.Column("signal_type", sa.String(80), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("subject_hash", sa.String(128), nullable=False),
        sa.Column("address_hash", sa.String(128), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("freshness_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "subject_hash", "signal_type", name="uq_signal_dedupe"),
    )
    op.create_index("ix_signals_zip_score", "signals", ["zip_code", "score"])
    op.create_table(
        "zip_signal_caches",
        sa.Column("zip_code", sa.String(10), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "behavioral_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.String(120), nullable=True),
        sa.Column("properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_behavioral_events_type_created", "behavioral_events", ["event_type", "created_at"])
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("signal_id", sa.Uuid(), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("outcome_type", sa.String(80), nullable=False),
        sa.Column("properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "market_health_scores",
        sa.Column("zip_code", sa.String(10), primary_key=True),
        sa.Column("score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("signal_density", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("provider_health", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.String(120), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])
    op.create_table(
        "dre_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("license_number", sa.String(80), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("provider_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("stripe_customer_id", sa.String(120), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(120), nullable=True, unique=True),
        sa.Column("plan_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="incomplete"),
        sa.Column("territory_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stripe_event_id", sa.String(160), nullable=False, unique=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cost_profile", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("data_source_id", sa.Uuid(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("zip_code", sa.String(10), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_normalized", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "raw_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ingestion_run_id", sa.Uuid(), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("source_record_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "daily_digests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "direct_mail_campaigns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("credit_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "letters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("direct_mail_campaigns.id"), nullable=False),
        sa.Column("signal_id", sa.Uuid(), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("lob_id", sa.String(120), nullable=True, unique=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("provider_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "mail_suppressions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("address_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "creator_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("creator_code", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("commission_rules", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("creator_source_id", sa.Uuid(), sa.ForeignKey("creator_sources.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("attribution_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "retention_scores",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("score", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "abuse_flags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("flag_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False, server_default="medium"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "disclaimer_acceptances",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("disclaimer_key", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "unit_economics_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope_type", sa.String(50), nullable=False),
        sa.Column("scope_id", sa.String(120), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("unit_economics_snapshots")
    op.drop_table("disclaimer_acceptances")
    op.drop_table("abuse_flags")
    op.drop_table("retention_scores")
    op.drop_table("referrals")
    op.drop_table("creator_sources")
    op.drop_table("mail_suppressions")
    op.drop_table("letters")
    op.drop_table("direct_mail_campaigns")
    op.drop_table("daily_digests")
    op.drop_table("raw_records")
    op.drop_table("ingestion_runs")
    op.drop_table("data_sources")
    op.drop_table("billing_events")
    op.drop_table("subscriptions")
    op.drop_table("dre_verifications")
    op.drop_table("audit_logs")
    op.drop_table("market_health_scores")
    op.drop_table("signal_outcomes")
    op.drop_table("behavioral_events")
    op.drop_table("zip_signal_caches")
    op.drop_table("signals")
    op.drop_table("provisioning_jobs")
    op.drop_table("territories")
    op.drop_table("kill_switches")
    op.drop_table("feature_flags")
    op.drop_table("tenant_memberships")
    op.drop_table("users")
    op.drop_table("tenants")
