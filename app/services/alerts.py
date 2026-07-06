from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sentry_sdk


def capture_critical_failure(
    name: str,
    exc: BaseException | None = None,
    *,
    context: Mapping[str, Any] | None = None,
) -> None:
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("zerohour.failure", name)
        if context:
            scope.set_context(name, _safe_context(context))
        if exc is not None:
            sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_message(name, level="error")


def _safe_context(context: Mapping[str, Any]) -> dict[str, Any]:
    redacted_keys = {
        "card",
        "card_number",
        "cvv",
        "jwt",
        "password",
        "passport_number",
        "payment_method",
        "payment_token",
        "token",
    }
    safe: dict[str, Any] = {}
    for key, value in context.items():
        if key.lower() in redacted_keys:
            safe[key] = "[redacted]"
        else:
            safe[key] = str(value)
    return safe
