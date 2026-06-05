from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.scoring import score_signal


def test_score_signal_rewards_confidence_and_freshness() -> None:
    recent = score_signal("probate", Decimal("0.90"), date.today())
    stale = score_signal("probate", Decimal("0.90"), date.today() - timedelta(days=300))

    assert recent > stale
    assert recent > Decimal("80")

