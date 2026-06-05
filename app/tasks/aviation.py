from __future__ import annotations

import asyncio
import uuid

from app.api.routes.aviation import process_signup_queue_item
from app.db.session import SessionLocal
from app.services.aviation_pipeline import PROOF_CARD_QUEUE, drain_flightaware_queue, generate_proof_card
from app.services.cache import redis_client
from app.workers.celery_app import celery_app


@celery_app.task(name="aviation.drain_flightaware_webhooks")
def drain_flightaware_webhooks(limit: int = 100) -> int:
    db = SessionLocal()
    try:
        return asyncio.run(drain_flightaware_queue(db, limit=limit))
    finally:
        db.close()


@celery_app.task(name="aviation.generate_proof_cards")
def generate_proof_cards(limit: int = 25) -> int:
    db = SessionLocal()
    processed = 0
    try:
        for _ in range(limit):
            signal_id = redis_client.rpop(PROOF_CARD_QUEUE)
            if not signal_id:
                break
            asyncio.run(generate_proof_card(db, uuid.UUID(signal_id)))
            processed += 1
        return processed
    finally:
        db.close()


@celery_app.task(name="aviation.process_signup_queue")
def process_signup_queue(limit: int = 250) -> int:
    db = SessionLocal()
    processed = 0
    try:
        for _ in range(limit):
            raw = redis_client.rpop("queue:signup")
            if not raw:
                break
            signal = uuid.UUID(__import__("json").loads(raw)["signup_queue_id"])
            asyncio.run(process_signup_queue_item(db, signal))
            processed += 1
        return processed
    finally:
        db.close()
