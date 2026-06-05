from __future__ import annotations

from datetime import datetime, timezone

from app.services.flight_options import SIGNAL_GREEN, build_rebooking_options


def test_build_rebooking_options_labels_fastest_cheapest_and_recommended() -> None:
    offers = [
        {
            "offer_id": "fastest",
            "airline": "United",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-03T12:00:00+00:00",
            "number_of_stops": 0,
            "layovers": [],
            "total_travel_time_minutes": 120,
            "cabin_class": "economy",
            "airline_logo_url": "https://example.com/ua.png",
            "total_price": "500.00",
            "currency": "USD",
        },
        {
            "offer_id": "cheapest",
            "airline": "Delta",
            "departure_time": "2026-06-03T10:30:00+00:00",
            "arrival_time": "2026-06-03T15:00:00+00:00",
            "number_of_stops": 1,
            "layovers": [{"airport": "ORD", "duration_minutes": 60}],
            "total_travel_time_minutes": 270,
            "cabin_class": "economy",
            "airline_logo_url": "https://example.com/dl.png",
            "total_price": "200.00",
            "currency": "USD",
        },
        {
            "offer_id": "balanced",
            "airline": "American",
            "departure_time": "2026-06-03T10:15:00+00:00",
            "arrival_time": "2026-06-03T13:00:00+00:00",
            "number_of_stops": 0,
            "layovers": [],
            "total_travel_time_minutes": 165,
            "cabin_class": "economy",
            "airline_logo_url": "https://example.com/aa.png",
            "total_price": "260.00",
            "currency": "USD",
        },
    ]

    options = build_rebooking_options(offers)

    assert [option["label"] for option in options] == [
        "Get there fastest",
        "Save the most",
        "ZeroHour Recommended",
    ]
    assert options[0]["offer_id"] == "fastest"
    assert options[1]["offer_id"] == "cheapest"
    assert options[2]["offer_id"] == "balanced"
    assert options[2]["is_default"] is True
    assert options[2]["badge_color"] == SIGNAL_GREEN
    assert options[2]["arrival_time"] == "2026-06-03T13:00:00+00:00"
    assert options[2]["number_of_stops"] == 0
    assert options[2]["total_travel_time_minutes"] == 165
    assert options[2]["airline_logo_url"] == "https://example.com/aa.png"
    assert options[2]["layovers"] == []
    assert options[2]["cabin_class"] == "economy"
    assert options[2]["total_price"] == "260.00"


def test_build_rebooking_options_filters_risky_and_nonviable_options() -> None:
    original_arrival = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    offers = [
        {
            "offer_id": "short-layover",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-03T13:00:00+00:00",
            "layovers": [{"airport": "DEN", "duration_minutes": 30}],
            "total_price": "200.00",
        },
        {
            "offer_id": "too-late",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-04T13:01:00+00:00",
            "layovers": [],
            "total_price": "100.00",
        },
        {
            "offer_id": "no-carry-on",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-03T13:00:00+00:00",
            "layovers": [],
            "cabin_class": "basic_economy",
            "carry_on_allowed": False,
            "total_price": "150.00",
        },
        {
            "offer_id": "viable",
            "airline": "Alaska",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-03T13:00:00+00:00",
            "layovers": [{"airport": "SEA", "duration_minutes": 45}],
            "cabin_class": "basic_economy",
            "carry_on_allowed": True,
            "total_price": "250.00",
        },
    ]

    options = build_rebooking_options(offers, original_scheduled_arrival=original_arrival)

    assert len(options) == 1
    assert options[0]["offer_id"] == "viable"
    assert options[0]["fare_warning"] == "Basic economy fare"
    assert options[0]["is_default"] is True
    assert options[0]["badge_color"] == SIGNAL_GREEN


def test_build_rebooking_options_does_not_duplicate_distinct_winners() -> None:
    options = build_rebooking_options(
        [
            {
                "offer_id": "best",
                "departure_time": "2026-06-03T10:00:00+00:00",
                "arrival_time": "2026-06-03T12:00:00+00:00",
                "total_price": "100.00",
            }
        ]
    )

    assert len(options) == 1
    assert options[0]["offer_id"] == "best"
