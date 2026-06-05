from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a signed mock FlightAware webhook.")
    parser.add_argument("--url", default="http://localhost:8000/webhooks/flightaware")
    parser.add_argument("--secret", default="dev-flightaware-secret")
    parser.add_argument("--flight-number", default="UA123")
    parser.add_argument("--webhook-id", default="mock-fa-UA123")
    args = parser.parse_args()

    payload = {
        "event_type": "operational_signal",
        "flight_number": args.flight_number,
        "flightaware_webhook_id": args.webhook_id,
        "fired_at": datetime.now(UTC).isoformat(),
        "indicators": {
            "crew_scheduling_pressure": 1,
            "maintenance_flag": 1,
            "weather_system_trajectory": 0.8,
            "atc_congestion": 0.7,
            "ground_stop": 0,
            "historical_delay_rate": 0.8,
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(args.secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    response = httpx.post(
        args.url,
        content=raw,
        headers={"Content-Type": "application/json", "X-FlightAware-Signature": f"sha256={signature}"},
        timeout=10,
    )
    print(response.status_code)
    print(response.text)


if __name__ == "__main__":
    main()
