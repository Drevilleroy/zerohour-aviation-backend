from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "zerohour",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.provisioning",
        "app.tasks.ingestion",
        "app.tasks.direct_mail",
        "app.tasks.billing",
        "app.tasks.notifications",
        "app.tasks.analytics",
        "app.tasks.aviation",
        "app.jobs.scheduler",
    ],
)

celery_app.conf.task_routes = {
    "app.tasks.provisioning.*": {"queue": "provisioning"},
    "app.tasks.ingestion.*": {"queue": "ingestion"},
    "app.tasks.direct_mail.*": {"queue": "direct_mail"},
    "app.tasks.billing.*": {"queue": "billing"},
    "app.tasks.notifications.*": {"queue": "notifications"},
    "app.tasks.analytics.*": {"queue": "analytics"},
    "app.tasks.aviation.*": {"queue": "aviation"},
    "aviation.*": {"queue": "aviation"},
    "app.jobs.scheduler.*": {"queue": "freight"},
}
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_default_retry_delay = 30
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "aviation-signup-queue-every-5-seconds": {
        "task": "aviation.process_signup_queue",
        "schedule": 5,
    },
    "aviation-flightaware-webhooks-every-5-seconds": {
        "task": "aviation.drain_flightaware_webhooks",
        "schedule": 5,
    },
    "aviation-proof-cards-every-30-seconds": {
        "task": "aviation.generate_proof_cards",
        "schedule": 30,
    },
    "refresh-market-health-hourly": {
        "task": "app.tasks.analytics.refresh_market_health",
        "schedule": 3600,
    },
    "generate-daily-digests": {
        "task": "app.tasks.notifications.generate_daily_digests",
        "schedule": 3600,
    },
    "compute-retention-risk-hourly": {
        "task": "app.tasks.analytics.compute_retention_risk",
        "schedule": 3600,
    },
    "aviation-price-alerts-every-6-hours": {
        "task": "aviation.monitor_price_alerts",
        "schedule": 21600,
    },
}
