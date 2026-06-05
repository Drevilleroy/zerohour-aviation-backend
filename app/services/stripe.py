from __future__ import annotations

import hashlib
import hmac
import time


class StripeSignatureError(Exception):
    pass


def verify_stripe_signature(
    *,
    payload: bytes,
    signature_header: str | None,
    webhook_secret: str | None,
    tolerance_seconds: int,
) -> None:
    if not webhook_secret:
        return
    if not signature_header:
        raise StripeSignatureError("Missing Stripe-Signature header")

    parts = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)

    timestamp_values = parts.get("t", [])
    signatures = parts.get("v1", [])
    if not timestamp_values or not signatures:
        raise StripeSignatureError("Malformed Stripe-Signature header")

    timestamp = int(timestamp_values[0])
    if abs(time.time() - timestamp) > tolerance_seconds:
        raise StripeSignatureError("Stripe webhook timestamp outside tolerance")

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeSignatureError("Invalid Stripe webhook signature")
