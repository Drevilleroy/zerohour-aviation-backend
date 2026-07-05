import { z } from "zod";

import { protectedProcedure, router } from "../../trpc";

import { authToken, zeroHourApi } from "./client";

export const alertsBridge = router({
  setPrice: protectedProcedure
    .input(
      z.object({
        flightId: z.string().min(1).optional(),
        currentPrice: z.number().nonnegative().optional(),
        tripId: z.string().min(1).optional(),
        targetPrice: z.number().nonnegative().optional(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi("/alerts/price", {
        method: "POST",
        token: authToken(ctx),
        body: {
          flightId: input.flightId,
          currentPrice: input.currentPrice ?? input.targetPrice,
          tripId: input.tripId,
          targetPrice: input.targetPrice,
        },
      });
    }),

  get: protectedProcedure.query(async ({ ctx }) => {
    return zeroHourApi("/alerts", {
      token: authToken(ctx),
    });
  }),
});
