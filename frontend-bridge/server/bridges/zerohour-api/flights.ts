import { z } from "zod";

import { protectedProcedure, router } from "../../trpc";

import { authToken, zeroHourApi } from "./client";

const flightSearchInput = z.object({
  departure: z.string().min(1),
  arrival: z.string().min(1),
  date: z.coerce.date(),
  passengers: z.number().int().min(1).max(9).default(1),
  loyaltyNumber: z.string().optional(),
  gclid: z.string().optional(),
});

export const flightsBridge = router({
  search: protectedProcedure.input(flightSearchInput).mutation(async ({ input, ctx }) => {
    return zeroHourApi("/flights/search", {
      method: "POST",
      token: authToken(ctx),
      body: {
        departure: input.departure,
        arrival: input.arrival,
        date: input.date.toISOString(),
        passengers: input.passengers,
        loyaltyNumber: input.loyaltyNumber,
        gclid: input.gclid,
      },
    });
  }),

  getResults: protectedProcedure
    .input(z.object({ offerId: z.string().min(1) }))
    .query(async ({ input, ctx }) => {
      return zeroHourApi(`/flights/offers/${encodeURIComponent(input.offerId)}`, {
        token: authToken(ctx),
      });
    }),

  book: protectedProcedure
    .input(
      z.object({
        offerId: z.string().min(1),
        passenger: z
          .object({
            name: z.string(),
            dateOfBirth: z.string(),
            passportNumber: z.string().optional(),
            email: z.string().email(),
            phone: z.string().optional(),
          })
          .optional(),
      }),
    )
    .mutation(async ({ input, ctx }) => {
      return zeroHourApi("/flights/book", {
        method: "POST",
        token: authToken(ctx),
        body: {
          offer_id: input.offerId,
          passenger: input.passenger
            ? {
                name: input.passenger.name,
                date_of_birth: input.passenger.dateOfBirth,
                passport_number: input.passenger.passportNumber,
                email: input.passenger.email,
                phone: input.passenger.phone,
              }
            : undefined,
        },
      });
    }),
});
