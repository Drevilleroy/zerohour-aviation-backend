from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.signal_claims import calculate_claim_delta_minutes


def test_calculate_claim_delta_minutes_is_floor_integer() -> None:
    fired_at = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

    assert calculate_claim_delta_minutes(fired_at, fired_at + timedelta(minutes=4)) == 4
    assert calculate_claim_delta_minutes(fired_at, fired_at + timedelta(minutes=31)) == 31
    assert calculate_claim_delta_minutes(fired_at, fired_at + timedelta(minutes=4, seconds=59)) == 4

