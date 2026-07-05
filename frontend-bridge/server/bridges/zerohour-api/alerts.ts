import { z } from "zod";

import { protectedProcedure, router } from "../../_core/trpc";

import { authToken, zeroHourApi } from "./client";

const priceAlertInput = z.object({
  flightId: z.string().min(1).optional(),
  currentPrice: z.number().nonnegative().optional(),
  tripId: z.string().min(1).optional(),
  targetPrice: z.number().nonnegative().optional(),
});
type PriceAlertInput = z.infer<typeof priceAlertInput>;

export const alertsBridge = router({
  setPrice: protectedProcedure
    .input(priceAlertInput)
    .mutation(async ({ input, ctx }: { input: PriceAlertInput; ctx: unknown }) => {
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

  get: protectedProcedure.query(async ({ ctx }: { ctx: unknown }) => {
    return zeroHourApi("/alerts", {
      token: authToken(ctx),
    });
  }),
});
