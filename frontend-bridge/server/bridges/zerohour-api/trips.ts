import { z } from "zod";

import { protectedProcedure, router } from "../../trpc";

import { authToken, zeroHourApi } from "./client";

export const tripsBridge = router({
  save: protectedProcedure
    .input(
      z.object({
        departure: z.string().min(1),
        arrival: z.string().min(1),
        date: z.coerce.date(),
        airline: z.string().optional(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi("/trips/save", {
        method: "POST",
        token: authToken(ctx),
        body: {
          departure: input.departure,
          arrival: input.arrival,
          date: input.date.toISOString(),
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
