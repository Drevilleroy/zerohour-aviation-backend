from __future__ import annotations

from app.services.new_flight_booking import _rank_new_booking_offers


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
