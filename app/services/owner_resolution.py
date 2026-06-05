from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.owner_resolution import MailingAddress
from app.services.cache import CacheKeys, get_json, increment_daily_counter, set_json


class OwnerResolutionRateLimitExceeded(Exception):
    pass


class OwnerResolutionRateLimitUnavailable(Exception):
    pass


@dataclass(frozen=True)
class OwnerResolutionResult:
    resolved: bool
    name: str | None = None
    mailing_address: dict | None = None

    @property
    def owner_last_name(self) -> str | None:
        if not self.name:
            return None
        parts = [part for part in self.name.replace(",", " ").split() if part]
        return parts[-1] if parts else None

    @property
    def salutation(self) -> str:
        if self.owner_last_name:
            return f"Dear {self.owner_last_name} Family,"
        return "Dear Homeowner,"


async def resolve_owner_for_user(*, user_id: UUID, address: str, zip_code: str) -> OwnerResolutionResult:
    normalized_address = _normalize_address(address)
    normalized_zip = _normalize_zip(zip_code)
    _enforce_owner_resolution_rate_limit(user_id)

    session_key = CacheKeys.owner_resolution_session(str(user_id), normalized_address, normalized_zip)
    cached = get_json(session_key)
    if cached:
        return OwnerResolutionResult(
            resolved=bool(cached.get("resolved")),
            name=cached.get("name"),
            mailing_address=cached.get("mailing_address"),
        )

    result = await _resolve_with_batchdata_or_mock(address=normalized_address, zip_code=normalized_zip)
    session_payload = {
        "resolved": result.resolved,
        "name": result.name,
        "mailing_address": result.mailing_address,
        "owner_last_name": result.owner_last_name,
        "letter_salutation": result.salutation,
        "lob_delivery_address": result.mailing_address
        if result.resolved
        else {"line1": normalized_address, "zip": normalized_zip},
    }
    set_json(
        session_key,
        session_payload,
        ttl_seconds=settings.owner_resolution_session_ttl_seconds,
    )
    return result


def get_cached_letter_context(*, user_id: UUID, address: str, zip_code: str) -> dict | None:
    session_key = CacheKeys.owner_resolution_session(
        str(user_id), _normalize_address(address), _normalize_zip(zip_code)
    )
    return get_json(session_key)


def fallback_letter_context(*, address: str, zip_code: str) -> dict:
    return {
        "resolved": False,
        "owner_last_name": None,
        "letter_salutation": "Dear Homeowner,",
        "lob_delivery_address": {"line1": _normalize_address(address), "zip": _normalize_zip(zip_code)},
    }


def _enforce_owner_resolution_rate_limit(user_id: UUID) -> None:
    key = CacheKeys.owner_resolution_rate_limit(str(user_id))
    try:
        count = increment_daily_counter(key)
    except RedisError as exc:
        raise OwnerResolutionRateLimitUnavailable("Owner resolution rate limiter is unavailable.") from exc
    if count > settings.owner_resolution_daily_limit:
        raise OwnerResolutionRateLimitExceeded("Owner resolution daily limit exceeded.")


async def _resolve_with_batchdata_or_mock(*, address: str, zip_code: str) -> OwnerResolutionResult:
    if settings.owner_resolution_mode == "mock" or not settings.batchdata_api_key:
        return _mock_owner_resolution(address=address, zip_code=zip_code)

    url = f"{settings.batchdata_base_url.rstrip('/')}/{settings.batchdata_owner_lookup_path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {settings.batchdata_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"address": address, "zip": zip_code}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    return _parse_batchdata_response(response.json())


def _parse_batchdata_response(payload: dict[str, Any]) -> OwnerResolutionResult:
    candidate = _first_object(
        payload.get("owner"),
        payload.get("owners"),
        payload.get("data"),
        payload.get("result"),
        payload.get("property", {}).get("owner") if isinstance(payload.get("property"), dict) else None,
    )
    if not candidate:
        return OwnerResolutionResult(resolved=False)

    name = (
        candidate.get("fullName")
        or candidate.get("full_name")
        or candidate.get("name")
        or candidate.get("ownerName")
    )
    mailing = (
        candidate.get("mailingAddress")
        or candidate.get("mailing_address")
        or candidate.get("mailing")
        or payload.get("mailingAddress")
    )
    mailing_address = _normalize_mailing_address(mailing)
    if not name or not mailing_address:
        return OwnerResolutionResult(resolved=False)
    return OwnerResolutionResult(resolved=True, name=str(name), mailing_address=mailing_address)


def _mock_owner_resolution(*, address: str, zip_code: str) -> OwnerResolutionResult:
    digest = hashlib.sha256(f"{address}:{zip_code}".encode("utf-8")).hexdigest()
    if int(digest[:2], 16) % 5 == 0:
        return OwnerResolutionResult(resolved=False)
    last_names = ["Carter", "Morales", "Kim", "Johnson", "Patel", "Rivera"]
    last_name = last_names[int(digest[2:4], 16) % len(last_names)]
    city = "Los Angeles" if zip_code.startswith("9") else "New York"
    state = "CA" if zip_code.startswith("9") else "NY"
    return OwnerResolutionResult(
        resolved=True,
        name=f"Taylor {last_name}",
        mailing_address={
            "line1": address,
            "line2": None,
            "city": city,
            "state": state,
            "zip": zip_code,
        },
    )


def _first_object(*values: Any) -> dict | None:
    for value in values:
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if isinstance(value, dict):
            return value
    return None


def _normalize_mailing_address(value: Any) -> dict | None:
    if isinstance(value, str):
        if not value.strip():
            return None
        return {"line1": value.strip(), "line2": None, "city": None, "state": None, "zip": None}
    if not isinstance(value, dict):
        return None
    line1 = value.get("line1") or value.get("street") or value.get("address") or value.get("address1")
    if not line1:
        return None
    mailing = MailingAddress(
        line1=str(line1),
        line2=value.get("line2") or value.get("address2"),
        city=value.get("city"),
        state=value.get("state"),
        zip=value.get("zip") or value.get("postalCode") or value.get("postal_code"),
    )
    return mailing.model_dump()


def _normalize_address(address: str) -> str:
    return " ".join(address.strip().split())


def _normalize_zip(zip_code: str) -> str:
    return "".join(ch for ch in zip_code if ch.isdigit())[:5]
