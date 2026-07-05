import { z } from "zod";

import { protectedProcedure, router } from "../../_core/trpc";

import { authToken, zeroHourApi } from "./client";

const tripSaveInput = z.object({
  flightId: z.string().optional(),
  price: z.number().nonnegative().optional(),
  departure: z.string().min(1).optional(),
  arrival: z.string().min(1).optional(),
  date: z.coerce.date().optional(),
  airline: z.string().optional(),
});
type TripSaveInput = z.infer<typeof tripSaveInput>;

const tripDeleteInput = z.object({ tripId: z.string().min(1) });
type TripDeleteInput = z.infer<typeof tripDeleteInput>;

export const tripsBridge = router({
  save: protectedProcedure
    .input(tripSaveInput)
    .mutation(async ({ input, ctx }: { input: TripSaveInput; ctx: unknown }) => {
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

  getSaved: protectedProcedure.query(async ({ ctx }: { ctx: unknown }) => {
    return zeroHourApi("/trips", {
      token: authToken(ctx),
    });
  }),

  delete: protectedProcedure
    .input(tripDeleteInput)
    .mutation(async ({ input, ctx }: { input: TripDeleteInput; ctx: unknown }) => {
      return zeroHourApi(`/trips/${encodeURIComponent(input.tripId)}`, {
        method: "DELETE",
        token: authToken(ctx),
      });
    }),
});
