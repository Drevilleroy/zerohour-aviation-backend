from __future__ import annotations

from celery.schedules import crontab
from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.engine.prophfesy import calculate_prediction_accuracy, run_prophfesy_engine
from app.engine.weekly_chain import (
    evaluate_reroute_triggers,
    generate_due_weekly_chains,
    generate_weekly_chains,
)
from app.integrations.dat_integration import run_dat_pipeline as run_dat_integration
from app.integrations.fred_integration import run_fred_pipeline as run_fred_integration
from app.integrations.weather_integration import run_weather_pipeline as run_weather_integration
from app.scrapers.fmcsa_scraper import run_fmcsa_pipeline as run_fmcsa_scraper
from app.scrapers.fuel_scraper import run_fuel_pipeline as run_fuel_scraper
from app.scrapers.port_scraper import run_port_scraper as run_port_volume_scraper
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


TASK_OPTIONS = {
    "bind": True,
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_jitter": True,
    "max_retries": 3,
}


@celery_app.task(**TASK_OPTIONS)
def run_dat_pipeline(self) -> dict:
    return _with_session(run_dat_integration)


@celery_app.task(**TASK_OPTIONS)
def run_weather_pipeline(self) -> dict:
    return _with_session(run_weather_integration)


@celery_app.task(**TASK_OPTIONS)
def run_fmcsa_pipeline(self) -> dict:
    return _with_session(run_fmcsa_scraper)


@celery_app.task(**TASK_OPTIONS)
def run_fuel_pipeline(self) -> dict:
    return _with_session(run_fuel_scraper)


@celery_app.task(**TASK_OPTIONS)
def run_port_scraper(self) -> dict:
    return _with_session(run_port_volume_scraper)


@celery_app.task(**TASK_OPTIONS)
def run_prophfesy_pipeline(self) -> dict:
    results = _with_session(run_prophfesy_engine)
    return {"status": "completed", "lanes_scored": len(results)}


@celery_app.task(**TASK_OPTIONS)
def run_fred_pipeline(self) -> dict:
    return _with_session(run_fred_integration)


@celery_app.task(**TASK_OPTIONS)
def calculate_prediction_accuracy_pipeline(self) -> dict:
    updated = _with_session(calculate_prediction_accuracy)
    return {"status": "completed", "predictions_updated": updated}


@celery_app.task(**TASK_OPTIONS)
def generate_weekly_load_chains(self) -> dict:
    chains = _with_session(generate_due_weekly_chains)
    for chain in chains:
        deliver_weekly_chain.apply_async(args=[str(chain.id)], queue="notifications")
    return {"status": "completed", "chains_generated": len(chains)}


@celery_app.task(**TASK_OPTIONS)
def generate_all_weekly_load_chains(self) -> dict:
    chains = _with_session(generate_weekly_chains)
    for chain in chains:
        deliver_weekly_chain.apply_async(args=[str(chain.id)], queue="notifications")
    return {"status": "completed", "chains_generated": len(chains)}


@celery_app.task(**TASK_OPTIONS)
def evaluate_weekly_chain_reroutes(self) -> dict:
    chains = _with_session(evaluate_reroute_triggers)
    for chain in chains:
        deliver_reroute_alert.apply_async(args=[str(chain.id)], queue="notifications")
    return {"status": "completed", "reroutes_generated": len(chains)}


@celery_app.task(**TASK_OPTIONS)
def deliver_weekly_chain(self, chain_id: str) -> dict:
    return {
        "status": "queued_provider_send",
        "chain_id": chain_id,
        "channels": ["push", "email", "dashboard"],
    }


@celery_app.task(**TASK_OPTIONS)
def deliver_reroute_alert(self, chain_id: str) -> dict:
    return {
        "status": "queued_provider_send",
        "chain_id": chain_id,
        "channels": ["push"],
        "sla_minutes": 15,
    }


def _with_session(fn):
    db = SessionLocal()
    try:
        result = fn(db)
        return result
    except Exception:
        db.rollback()
        logger.exception(
            "freight_pipeline_failed",
            extra={"pipeline": getattr(fn, "__name__", "unknown")},
        )
        raise
    finally:
        db.close()


celery_app.conf.beat_schedule.update(
    {
        "freight-dat-every-4-hours": {
            "task": "app.jobs.scheduler.run_dat_pipeline",
            "schedule": crontab(minute=0, hour="*/4"),
        },
        "freight-weather-every-6-hours": {
            "task": "app.jobs.scheduler.run_weather_pipeline",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "freight-fmcsa-daily-5am-utc": {
            "task": "app.jobs.scheduler.run_fmcsa_pipeline",
            "schedule": crontab(minute=0, hour=5),
        },
        "freight-fuel-daily-6am-utc": {
            "task": "app.jobs.scheduler.run_fuel_pipeline",
            "schedule": crontab(minute=0, hour=6),
        },
        "freight-port-monday-8am-pacific": {
            "task": "app.jobs.scheduler.run_port_scraper",
            "schedule": crontab(minute=0, hour=16, day_of_week="mon"),
        },
        "freight-prophfesy-hourly": {
            "task": "app.jobs.scheduler.run_prophfesy_pipeline",
            "schedule": crontab(minute=0),
        },
        "freight-accuracy-every-72-hours": {
            "task": "app.jobs.scheduler.calculate_prediction_accuracy_pipeline",
            "schedule": 259200,
        },
        "freight-fred-daily": {
            "task": "app.jobs.scheduler.run_fred_pipeline",
            "schedule": crontab(minute=15, hour=7),
        },
        "freight-weekly-load-chain-local-8pm-check": {
            "task": "app.jobs.scheduler.generate_weekly_load_chains",
            "schedule": crontab(minute=0),
        },
        "freight-weekly-chain-reroute-monitor": {
            "task": "app.jobs.scheduler.evaluate_weekly_chain_reroutes",
            "schedule": 900,
        },
    }
)
