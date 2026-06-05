from __future__ import annotations

import hashlib
import hmac

from app.services.aviation_security import verify_hmac_sha256


def test_flightaware_hmac_accepts_valid_signature() -> None:
    raw = b'{"flight_number":"UA123"}'
    secret = "secret"
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256(raw, f"sha256={signature}", secret) is True


def test_flightaware_hmac_rejects_invalid_signature() -> None:
    assert verify_hmac_sha256(b"{}", "sha256=bad", "secret") is False
