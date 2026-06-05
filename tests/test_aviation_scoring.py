from __future__ import annotations

from app.services.aviation_scoring import score_signal


def test_prophfesy_high_confidence_signal() -> None:
    result = score_signal(
        {
            "indicators": {
                "crew_scheduling_pressure": 1,
                "maintenance_flag": 1,
                "weather_system_trajectory": 1,
                "atc_congestion": 1,
                "ground_stop": 1,
                "historical_delay_rate": 1,
            }
        }
    )

    assert result.score == 100
    assert result.should_alert is True
    assert result.high_confidence is True


def test_prophfesy_below_threshold_does_not_alert() -> None:
    result = score_signal({"indicators": {"historical_delay_rate": 1, "ground_stop": 1}})

    assert result.score == 20
    assert result.should_alert is False
    assert result.high_confidence is False
