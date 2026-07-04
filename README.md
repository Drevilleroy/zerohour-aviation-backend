# ZeroHour Aviation Backend

Production-oriented FastAPI backend for FlyZeroHour.com, a flight disruption intelligence
and direct-airline booking platform.

ZeroHour helps travelers search flights, pick from Best Value / Fastest / Cheapest options,
book directly with airlines with no ZeroHour markup, save trips, set price alerts, and monitor
booked flights for early disruption signals.

## Core Capabilities

- Flight search backed by Duffel, with mock-mode fallbacks for local development
- Three-card booking engine response: `bestValue`, `fastest`, `cheapest`, `allResults`
- Direct airline booking links with ZeroHour referral tracking and no commission marker
- Protected trip handoffs that start FlightAware monitoring after the user chooses a flight
- Saved trips, price alerts, booking history, and search analytics
- Six-hour price alert monitor with email and push notification hooks
- Stripe-backed subscription signup for ZeroHour membership
- FlightAware webhook processing for disruption intelligence

## Start Locally

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

## Useful Commands

```bash
make migrate
make test
.venv312/bin/python -m pytest
```

## Frontend Contract For Manus

Primary customer journey endpoints:

- `POST /flights/search`
- `GET /flights/offers/{offer_id}`
- `POST /flights/book`
- `GET /flights/bookings/{order_id}`
- `POST /trips/save`
- `GET /trips`
- `DELETE /trips/{trip_id}`
- `POST /alerts/price`
- `GET /alerts`
- `POST /bookings/log`
- `GET /bookings/history`

The main search endpoint accepts either the frontend-friendly fields:

```json
{
  "departure": "New York",
  "arrival": "LA",
  "date": "2026-07-10T00:00:00Z",
  "passengers": 1,
  "loyaltyNumber": "UA123",
  "gclid": "optional-google-click-id"
}
```

or the lower-level aviation fields:

```json
{
  "origin": "NYC",
  "destination": "LAX",
  "departure_date": "2026-07-10T00:00:00Z",
  "passenger_count": 1
}
```

It returns:

```json
{
  "bestValue": { "flightId": "off_123", "directBookingUrl": "https://..." },
  "fastest": { "flightId": "off_456", "directBookingUrl": "https://..." },
  "cheapest": { "flightId": "off_789", "directBookingUrl": "https://..." },
  "allResults": [],
  "cacheStatus": "fresh"
}
```

## Environment

Important production integrations are configured through environment variables:

- `DUFFEL_API_KEY`
- `FLIGHTAWARE_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `POSTMARK_API_KEY`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `REDIS_URL`
- `DATABASE_URL`

When provider keys are absent or mock-mode keys are used, the backend returns deterministic mock
flight data so the frontend can develop safely without hitting live systems.
