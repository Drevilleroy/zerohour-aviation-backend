import { z } from "zod";

import { protectedProcedure, publicProcedure, router } from "../../_core/trpc";

import { authToken, zeroHourApi } from "./client";

const flightSearchInput = z.object({
  departure: z.string().min(1),
  arrival: z.string().min(1),
  date: z.coerce.date(),
  passengers: z.number().int().min(1).max(9).default(1),
  loyaltyNumber: z.string().optional(),
  gclid: z.string().optional(),
});
type FlightSearchInput = z.infer<typeof flightSearchInput>;

const offerIdInput = z.object({ offerId: z.string().min(1) });
type OfferIdInput = z.infer<typeof offerIdInput>;

const bookInput = z.object({
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
});
type BookInput = z.infer<typeof bookInput>;

export const flightsBridge = router({
  search: publicProcedure.input(flightSearchInput).mutation(async ({
    input,
    ctx,
  }: {
    input: FlightSearchInput;
    ctx: unknown;
  }) => {
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

  getResults: publicProcedure
    .input(offerIdInput)
    .query(async ({ input, ctx }: { input: OfferIdInput; ctx: unknown }) => {
      return zeroHourApi(`/flights/offers/${encodeURIComponent(input.offerId)}`, {
        token: authToken(ctx),
      });
    }),

  book: protectedProcedure
    .input(bookInput)
    .mutation(async ({ input, ctx }: { input: BookInput; ctx: unknown }) => {
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
