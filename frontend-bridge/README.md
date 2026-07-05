# ZeroHour tRPC Bridge For Manus Frontend

Copy `server/bridges/zerohour-api/` into the Manus frontend repo at the same path:

```text
server/bridges/zerohour-api/
  client.ts
  flights.ts
  trips.ts
  alerts.ts
  bookings.ts
  index.ts
```

## Environment

Add this to the frontend runtime environment:

```env
ZEROHOUR_API_BASE_URL=https://zerohour-aviation-backend-production.up.railway.app
```

Update `server/_core/env.ts`:

```ts
export const ENV = {
  // existing values...
  zerohourApiBaseUrl: process.env.ZEROHOUR_API_BASE_URL ?? "",
};
```

## Router Wiring

In `server/routers.ts`:

```ts
import {
  alertsBridge,
  bookingsBridge,
  flightsBridge,
  tripsBridge,
} from "./bridges/zerohour-api";

export const appRouter = router({
  // existing routers...
  flights: flightsBridge,
  trips: tripsBridge,
  alerts: alertsBridge,
  bookings: bookingsBridge,
});
```

## Assumptions To Verify In Manus Repo

The bridge imports these symbols:

```ts
import { protectedProcedure, router } from "../../trpc";
import { ENV } from "../../_core/env";
```

If the Manus frontend uses different local paths, adjust those two imports in each bridge file.

The bridge expects the auth token at one of:

- `ctx.user.token`
- `ctx.user.accessToken`
- `ctx.session.accessToken`

If Manus stores the bearer token elsewhere, update `authToken()` in `client.ts`.

## Procedures

- `flights.search`
- `flights.getResults`
- `flights.book`
- `trips.save`
- `trips.getSaved`
- `trips.delete`
- `alerts.setPrice`
- `alerts.get`
- `bookings.logBooking`
- `bookings.getHistory`

## Compatible Call Shapes

The bridge accepts the card-based calls Manus currently shows in the UI:

```ts
trpc.booking.trips.save.mutate({ flightId, price });
trpc.booking.alerts.setPrice.mutate({ tripId, targetPrice });
```

It also accepts the fuller explicit trip shape:

```ts
trpc.booking.trips.save.mutate({
  departure: "NYC",
  arrival: "LAX",
  date: new Date("2026-07-10"),
  airline: "United",
});
```
