from __future__ import annotations

from datetime import UTC, datetime

from app.services.new_flight_booking import (
    _build_direct_booking_url,
    _filter_viable_offers,
    _label_ranked_offers,
    _rank_new_booking_offers,
)


def test_rank_new_booking_offers_prioritizes_zerohour_score_then_price_then_fastest() -> None:
    offers = [
        {
            "offer_id": "cheap-risky",
            "total_price": "100.00",
            "arrival_time": "2026-06-03T12:00:00+00:00",
            "zerohour_score": 90,
        },
        {
            "offer_id": "recommended",
            "total_price": "250.00",
            "arrival_time": "2026-06-03T14:00:00+00:00",
            "zerohour_score": 10,
        },
        {
            "offer_id": "fast-mid",
            "total_price": "300.00",
            "arrival_time": "2026-06-03T11:00:00+00:00",
            "zerohour_score": 50,
        },
    ]

    ranked = _rank_new_booking_offers(offers)

    assert [offer["offer_id"] for offer in ranked] == ["recommended", "cheap-risky", "fast-mid"]
    assert ranked[0]["zerohour_recommendation_score"] < ranked[1]["zerohour_recommendation_score"]


def test_rank_new_booking_offers_accounts_for_arrival_deadline_and_labels() -> None:
    offers = [
        {
            "offer_id": "cheap-too-late",
            "total_price": "100.00",
            "departure_time": "2026-06-03T09:00:00+00:00",
            "arrival_time": "2026-06-03T16:30:00+00:00",
            "total_travel_time_minutes": 450,
            "number_of_stops": 1,
            "zerohour_score": 10,
        },
        {
            "offer_id": "protected-fit",
            "total_price": "180.00",
            "departure_time": "2026-06-03T10:00:00+00:00",
            "arrival_time": "2026-06-03T14:00:00+00:00",
            "total_travel_time_minutes": 240,
            "number_of_stops": 0,
            "zerohour_score": 20,
        },
    ]

    ranked = _rank_new_booking_offers(
        offers,
        latest_arrival_time=datetime(2026, 6, 3, 15, 0, tzinfo=UTC),
        nonstop_preferred=True,
    )
    _label_ranked_offers(ranked)

    assert ranked[0]["offer_id"] == "protected-fit"
    assert "ZeroHour Pick" in ranked[0]["recommendation_label"]


def test_filter_viable_offers_honors_departure_arrival_and_stop_constraints() -> None:
    offers = [
        {
            "offer_id": "early",
            "departure_time": "2026-06-03T07:00:00+00:00",
            "arrival_time": "2026-06-03T10:00:00+00:00",
            "number_of_stops": 0,
        },
        {
            "offer_id": "too-many-stops",
            "departure_time": "2026-06-03T09:00:00+00:00",
            "arrival_time": "2026-06-03T13:00:00+00:00",
            "number_of_stops": 2,
        },
        {
            "offer_id": "fit",
            "departure_time": "2026-06-03T09:30:00+00:00",
            "arrival_time": "2026-06-03T12:30:00+00:00",
            "number_of_stops": 0,
        },
    ]

    viable = _filter_viable_offers(
        offers,
        earliest_departure_time=datetime(2026, 6, 3, 8, 0, tzinfo=UTC),
        latest_arrival_time=datetime(2026, 6, 3, 14, 0, tzinfo=UTC),
        max_stops=1,
    )

    assert [offer["offer_id"] for offer in viable] == ["fit"]


def test_build_direct_booking_url_uses_airline_site_with_search_context() -> None:
    url = _build_direct_booking_url(
        {
            "offer_id": "off_123",
            "airline": "United Airlines",
            "origin": "SFO",
            "destination": "JFK",
            "departure_time": "2026-06-03T09:30:00+00:00",
            "cabin_class": "economy",
        }
    )

    assert url.startswith("https://www.united.com/")
    assert "origin=SFO" in url
    assert "destination=JFK" in url
    assert "zh_source=zero_hour_direct" in url
