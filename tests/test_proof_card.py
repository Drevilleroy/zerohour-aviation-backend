from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.proof_card import render_proof_card_png

PIL = pytest.importorskip("PIL")


def test_render_proof_card_png_dimensions() -> None:
    fired_at = datetime(2026, 6, 3, 10, 15, tzinfo=timezone.utc)
    signal = SimpleNamespace(
        id=uuid4(),
        fired_at=fired_at,
        airline_announced_at=fired_at + timedelta(hours=2, minutes=35),
        head_start_minutes=155,
        score=87,
    )
    flight = SimpleNamespace(
        flight_number="UA123",
        origin="SFO",
        destination="JFK",
        departure_date=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
    )

    png = render_proof_card_png(signal, flight)

    assert png.startswith(b"\x89PNG")
    image = PIL.Image.open(BytesIO(png))
    assert image.size == (1080, 1080)
