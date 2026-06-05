from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.billing import PLANS, persist_stripe_event
from app.services.stripe import StripeSignatureError, verify_stripe_signature
from app.tasks.billing import reconcile_stripe_event

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
def plans() -> dict:
    return {"plans": [{"key": key, **value} for key, value in PLANS.items()]}


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    raw_body = await request.body()
    try:
        verify_stripe_signature(
            payload=raw_body,
            signature_header=stripe_signature,
            webhook_secret=settings.stripe_webhook_secret,
            tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
        )
        payload = json.loads(raw_body.decode("utf-8"))
    except StripeSignatureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event, created = persist_stripe_event(
        db,
        event_id=payload["id"],
        event_type=payload["type"],
        payload=payload,
    )
    db.commit()
    if created:
        reconcile_stripe_event.apply_async(args=[event.stripe_event_id], queue="billing")
    return {
        "status": "accepted" if created else "duplicate_ignored",
        "event_id": event.stripe_event_id,
        "message": "Event persisted idempotently; entitlement refresh should run from billing queue.",
        "has_signature": bool(stripe_signature),
    }
