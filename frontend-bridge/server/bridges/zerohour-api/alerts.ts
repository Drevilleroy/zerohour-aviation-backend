import { z } from "zod";

import { protectedProcedure, router } from "../../trpc";

import { authToken, zeroHourApi } from "./client";

export const alertsBridge = router({
  setPrice: protectedProcedure
    .input(
      z.object({
        flightId: z.string().min(1),
        currentPrice: z.number().nonnegative(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi("/alerts/price", {
        method: "POST",
        token: authToken(ctx),
        body: {
          flightId: input.flightId,
          currentPrice: input.currentPrice,
        },
      });
    }),

  get: protectedProcedure.query(async ({ ctx }) => {
    return zeroHourApi("/alerts", {
      token: authToken(ctx),
    });
  }),
});
