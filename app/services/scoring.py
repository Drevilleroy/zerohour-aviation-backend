from __future__ import annotations

from datetime import date
from decimal import Decimal


SIGNAL_WEIGHTS = {
    "probate": Decimal("95"),
    "divorce": Decimal("80"),
    "tax_delinquency": Decimal("85"),
    "permit_activity": Decimal("55"),
    "stale_listing": Decimal("60"),
    "ownership_duration": Decimal("40"),
    "absentee_ownership": Decimal("50"),
    "insurance_distress": Decimal("75"),
}


def score_signal(signal_type: str, confidence: Decimal, event_date: date | None) -> Decimal:
    base = SIGNAL_WEIGHTS.get(signal_type, Decimal("35"))
    freshness_multiplier = Decimal("1")
    if event_date:
        age_days = max((date.today() - event_date).days, 0)
        freshness_multiplier = max(Decimal("0.25"), Decimal("1") - (Decimal(age_days) / Decimal("365")))
    return (base * confidence * freshness_multiplier).quantize(Decimal("0.0001"))

