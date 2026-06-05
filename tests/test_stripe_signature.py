from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.services.stripe import StripeSignatureError, verify_stripe_signature


def test_verify_stripe_signature_accepts_valid_header() -> None:
    payload = b'{"id":"evt_123","type":"checkout.session.completed"}'
    secret = "whsec_test"
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()

    verify_stripe_signature(
        payload=payload,
        signature_header=f"t={timestamp},v1={digest}",
        webhook_secret=secret,
        tolerance_seconds=300,
    )


def test_verify_stripe_signature_rejects_invalid_header() -> None:
    with pytest.raises(StripeSignatureError):
        verify_stripe_signature(
            payload=b"{}",
            signature_header="t=123,v1=bad",
            webhook_secret="whsec_test",
            tolerance_seconds=300,
        )

