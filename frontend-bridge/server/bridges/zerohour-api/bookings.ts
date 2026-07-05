import { z } from "zod";

import { protectedProcedure, router } from "../../_core/trpc";

import { authToken, zeroHourApi } from "./client";

const bookingLogInput = z.object({
  flightId: z.string().min(1),
  airline: z.string().min(1),
  price: z.number().nonnegative(),
  bookingRef: z.string().optional(),
});
type BookingLogInput = z.infer<typeof bookingLogInput>;

export const bookingsBridge = router({
  logBooking: protectedProcedure
    .input(bookingLogInput)
    .mutation(async ({ input, ctx }: { input: BookingLogInput; ctx: unknown }) => {
      return zeroHourApi("/bookings/log", {
        method: "POST",
        token: authToken(ctx),
        body: {
          flightId: input.flightId,
          airline: input.airline,
          price: input.price,
          bookingRef: input.bookingRef,
        },
      });
    }),

  getHistory: protectedProcedure.query(async ({ ctx }: { ctx: unknown }) => {
    return zeroHourApi("/bookings/history", {
      token: authToken(ctx),
    });
  }),
});
