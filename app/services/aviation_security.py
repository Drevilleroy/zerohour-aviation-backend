from __future__ import annotations

import base64
import hashlib
import hmac
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def verify_hmac_sha256(raw_body: bytes, signature: str | None, secret: str | None) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, supplied)


def passenger_cipher() -> Fernet:
    digest = hashlib.sha256(settings.passenger_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_passenger_value(value: str | None) -> str | None:
    if value is None:
        return None
    return passenger_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_passenger_value(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return passenger_cipher().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
