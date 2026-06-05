from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Lane, Signal

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"

CORRIDORS = {
    "I-10": ["Los Angeles,US", "Phoenix,US", "El Paso,US", "San Antonio,US", "Houston,US"],
    "I-40": ["Los Angeles,US", "Albuquerque,US", "Oklahoma City,US", "Memphis,US"],
    "I-80": ["San Francisco,US", "Salt Lake City,US", "Chicago,US"],
    "I-5": ["San Diego,US", "Los Angeles,US", "Sacramento,US", "Portland,US", "Seattle,US"],
    "I-90": ["Seattle,US", "Spokane,US", "Billings,US", "Chicago,US"],
}


def run_weather_pipeline(db: Session) -> dict:
    if not settings.openweather_api_key:
        return {"status": "skipped", "reason": "missing OpenWeather API key"}
    lanes = db.query(Lane).all()
    if not lanes:
        return {"status": "skipped", "reason": "no tracked lanes"}

    disruptions = {}
    with httpx.Client(timeout=20) as client:
        for corridor, cities in CORRIDORS.items():
            events = [_fetch_city_forecast(client, city) for city in cities]
            severity = max((_weather_severity(event) for event in events if event), default=0)
            disruptions[corridor] = severity

    created = 0
    for lane in lanes:
        corridor, severity = max(disruptions.items(), key=lambda item: item[1])
        direction = "UP" if severity >= 2 else "NEUTRAL"
        if direction == "NEUTRAL":
            continue
        db.add(
            Signal(
                lane_id=lane.id,
                zip_code=lane.origin_zip,
                signal_type="WEATHER",
                signal_value={"corridor": corridor, "severity": severity},
                source="OpenWeatherMap",
                direction=direction,
                weight=Decimal("0.10"),
                subject_hash=f"weather:{lane.id}:{corridor}:{_bucket()}",
                confidence=Decimal("0.7000"),
                score=Decimal("0.10"),
                payload={"corridor": corridor, "severity": severity},
            )
        )
        created += 1
    db.commit()
    return {"status": "completed", "signals_created": created}


def _fetch_city_forecast(client: httpx.Client, city: str) -> dict | None:
    response = client.get(
        OPENWEATHER_URL,
        params={"q": city, "appid": settings.openweather_api_key, "units": "imperial"},
    )
    response.raise_for_status()
    return response.json()


def _weather_severity(payload: dict) -> int:
    severity = 0
    for item in payload.get("list", [])[:16]:
        weather_text = " ".join(
            w.get("main", "") + " " + w.get("description", "")
            for w in item.get("weather", [])
        )
        wind = item.get("wind", {}).get("speed", 0)
        if any(term in weather_text.lower() for term in ["snow", "storm", "tornado", "ice"]):
            severity = max(severity, 3)
        elif any(term in weather_text.lower() for term in ["rain", "fog"]) or wind >= 30:
            severity = max(severity, 2)
    return severity


def _bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H")
