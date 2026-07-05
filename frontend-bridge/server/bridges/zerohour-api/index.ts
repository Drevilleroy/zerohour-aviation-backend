import { router } from "../../_core/trpc";

import { alertsBridge } from "./alerts";
import { bookingsBridge } from "./bookings";
import { flightsBridge } from "./flights";
import { tripsBridge } from "./trips";

export { alertsBridge } from "./alerts";
export { bookingsBridge } from "./bookings";
export { flightsBridge } from "./flights";
export { tripsBridge } from "./trips";

export const bookingBridge = router({
  alerts: alertsBridge,
  bookings: bookingsBridge,
  flights: flightsBridge,
  trips: tripsBridge,
});
