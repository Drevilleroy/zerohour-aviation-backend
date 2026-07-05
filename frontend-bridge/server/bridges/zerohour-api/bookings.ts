import { z } from "zod";

import { protectedProcedure, router } from "../../_core/trpc";

import { authToken, zeroHourApi } from "./client";

export const bookingsBridge = router({
  logBooking: protectedProcedure
    .input(
      z.object({
        flightId: z.string().min(1),
        airline: z.string().min(1),
        price: z.number().nonnegative(),
        bookingRef: z.string().optional(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
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

  getHistory: protectedProcedure.query(async ({ ctx }) => {
    return zeroHourApi("/bookings/history", {
      token: authToken(ctx),
    });
  }),
});
