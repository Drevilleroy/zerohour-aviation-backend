from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import app.services.flight_booking_engine as booking_engine
from app.models import SavedTrip
from app.services.flight_booking_engine import (
    build_search_envelope,
    normalize_airport,
    save_trip,
    set_price_alert,
)


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


class FakeDB:
    def __init__(self) -> None:
        self.objects = []
        self.refreshed = []

    def add(self, obj) -> None:
        self.objects.append(obj)

    def commit(self) -> None:
        for obj in self.objects:
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime(2026, 7, 4, tzinfo=UTC)
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    def refresh(self, obj) -> None:
        self.refreshed.append(obj)

    def get(self, model, item_id):
        return next(
            (obj for obj in self.objects if isinstance(obj, model) and str(obj.id) == str(item_id)),
            None,
        )


def test_save_trip_can_resolve_selected_flight_from_cached_offer(monkeypatch) -> None:
    def fake_get_json(key: str):
        if key == "duffel:offer:off_save":
            return {
                "offer_id": "off_save",
                "origin": "NYC",
                "destination": "LAX",
                "departure_time": "2026-07-10T09:00:00+00:00",
                "airline": "United",
                "total_price": "260.00",
                "currency": "USD",
                "direct_booking_url": "https://www.united.com/search",
            }
        return None

    monkeypatch.setattr(booking_engine, "get_json", fake_get_json)
    db = FakeDB()

    trip = save_trip(db, user_id=uuid4(), flight_id="off_save", price=Decimal("260.00"))

    assert trip.flight_id == "off_save"
    assert trip.departure == "NYC"
    assert trip.arrival == "LAX"
    assert trip.airline == "United"
    assert trip.direct_booking_url == "https://www.united.com/search"


def test_set_price_alert_can_use_saved_trip_id() -> None:
    db = FakeDB()
    user_id = uuid4()
    trip = SavedTrip(
        user_id=user_id,
        flight_id="off_alert",
        departure="NYC",
        arrival="LAX",
        date=datetime(2026, 7, 10, tzinfo=UTC),
        airline="United",
        price=Decimal("260.00"),
        currency="USD",
        direct_booking_url="https://www.united.com/search",
    )
    db.add(trip)
    db.commit()

    alert = set_price_alert(db, user_id=user_id, trip_id=trip.id, current_price=Decimal("240.00"))

    assert alert.flight_id == "off_alert"
    assert alert.departure == "NYC"
    assert alert.arrival == "LAX"
