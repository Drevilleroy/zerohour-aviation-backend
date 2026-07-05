import { TRPCError } from "@trpc/server";

import { ENV } from "../../_core/env";

type Method = "GET" | "POST" | "DELETE";

export async function zeroHourApi<T>(
  path: string,
  options: {
    method?: Method;
    token?: string;
    body?: unknown;
  } = {},
): Promise<T> {
  if (!ENV.zerohourApiBaseUrl) {
    throw new TRPCError({
      code: "INTERNAL_SERVER_ERROR",
      message: "ZEROHOUR_API_BASE_URL is not configured",
    });
  }

  const response = await fetch(`${ENV.zerohourApiBaseUrl}${path}`, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let message = `ZeroHour API request failed: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload?.detail ?? payload?.message ?? message;
    } catch {
      // Keep the status-based message when the backend returns non-JSON.
    }
    throw new TRPCError({
      code: response.status === 401 ? "UNAUTHORIZED" : "INTERNAL_SERVER_ERROR",
      message,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function authToken(ctx: unknown): string | undefined {
  const maybeCtx = ctx as {
    user?: { token?: string; accessToken?: string };
    session?: { accessToken?: string };
  };
  return maybeCtx.user?.token ?? maybeCtx.user?.accessToken ?? maybeCtx.session?.accessToken;
}
