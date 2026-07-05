import { z } from "zod";

import { protectedProcedure, router } from "../../trpc";

import { authToken, zeroHourApi } from "./client";

export const tripsBridge = router({
  save: protectedProcedure
    .input(
      z.object({
        flightId: z.string().optional(),
        price: z.number().nonnegative().optional(),
        departure: z.string().min(1).optional(),
        arrival: z.string().min(1).optional(),
        date: z.coerce.date().optional(),
        airline: z.string().optional(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi("/trips/save", {
        method: "POST",
        token: authToken(ctx),
        body: {
          flightId: input.flightId,
          price: input.price,
          departure: input.departure,
          arrival: input.arrival,
          date: input.date?.toISOString(),
          airline: input.airline,
        },
      });
    }),

  getSaved: protectedProcedure.query(async ({ ctx }) => {
    return zeroHourApi("/trips", {
      token: authToken(ctx),
    });
  }),

  delete: protectedProcedure
    .input(z.object({ tripId: z.string().min(1) }))
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi(`/trips/${encodeURIComponent(input.tripId)}`, {
        method: "DELETE",
        token: authToken(ctx),
      });
    }),
});
