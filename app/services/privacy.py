from __future__ import annotations

from app.models import Signal

HOMEOWNER_PRIVATE_KEYS = {
    "owner",
    "owner_name",
    "owner_full_name",
    "homeowner_name",
    "first_name",
    "last_name",
    "mailing_address",
    "mailingAddress",
    "owner_mailing_address",
    "owner_profile",
}


def extract_signal_address(signal: Signal) -> str | None:
    for key in ("address", "display_address", "property_address", "street_address"):
        value = signal.payload.get(key)
        if value:
            return str(value)
    return None


def public_signal_card(signal: Signal) -> dict:
    return {
        "id": signal.id,
        "zip_code": signal.zip_code,
        "address": extract_signal_address(signal),
        "type": signal.signal_type,
        "score": float(signal.score),
        "confidence": float(signal.confidence),
        "freshness_days": signal.freshness_days,
        "source": signal.source,
        "signal_fired_at": signal.signal_fired_at,
        "signal_claimed_at": signal.signal_claimed_at,
        "claimed_by_user_id": signal.claimed_by_user_id,
        "claim_delta_minutes": signal.claim_delta_minutes,
    }


def sanitized_signal_payload(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in HOMEOWNER_PRIVATE_KEYS}

