from __future__ import annotations

from app.services.flight_booking_engine import build_search_envelope, normalize_airport


def test_normalize_airport_accepts_city_style_input() -> None:
    assert normalize_airport("New York") == "NYC"
    assert normalize_airport("LA") == "LAX"
    assert normalize_airport("sfo") == "SFO"


def test_build_search_envelope_returns_three_distinct_ranked_cards_when_possible() -> None:
    envelope = build_search_envelope(
        [
            {
                "offer_id": "value",
                "airline": "United",
                "flight_number": "UA100",
                "departure_time": "2026-07-10T09:00:00+00:00",
                "arrival_time": "2026-07-10T14:00:00+00:00",
                "total_travel_time_minutes": 300,
                "number_of_stops": 0,
                "total_price": "260.00",
                "currency": "USD",
                "available_seats": 7,
                "direct_booking_url": "https://www.united.com/search?origin=NYC",
                "zerohour_score": 18,
            },
            {
                "offer_id": "fastest",
                "airline": "Delta",
                "flight_number": "DL200",
                "departure_time": "2026-07-10T10:00:00+00:00",
                "arrival_time": "2026-07-10T14:15:00+00:00",
                "total_travel_time_minutes": 255,
                "number_of_stops": 0,
                "total_price": "410.00",
                "currency": "USD",
                "available_seats": 3,
                "direct_booking_url": "https://www.delta.com/search",
                "zerohour_score": 12,
            },
            {
                "offer_id": "cheapest",
                "airline": "American",
                "flight_number": "AA300",
                "departure_time": "2026-07-10T06:00:00+00:00",
                "arrival_time": "2026-07-10T15:30:00+00:00",
                "total_travel_time_minutes": 570,
                "number_of_stops": 1,
                "total_price": "180.00",
                "currency": "USD",
                "available_seats": 9,
                "direct_booking_url": "https://www.aa.com/search",
                "zerohour_score": 30,
            },
        ],
        passengers=2,
        loyalty_number="UA123",
    )

    assert envelope["bestValue"]["flightId"] == "value"
    assert envelope["fastest"]["flightId"] == "fastest"
    assert envelope["cheapest"]["flightId"] == "cheapest"
    assert "Best Value" in envelope["bestValue"]["badges"]
    assert "Fastest" in envelope["fastest"]["badges"]
    assert "Cheapest" in envelope["cheapest"]["badges"]
    assert "zh_ref=ZEROHOUR_DIRECT" in envelope["bestValue"]["directBookingUrl"]
    assert "loyaltyNumber=UA123" in envelope["bestValue"]["directBookingUrl"]
    assert envelope["bestValue"]["loyalty"]["estimatedMiles"] == 2400
