"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/services/api-error";
import { getHealth } from "@/services/api";

export const healthQueryKey = ["health"] as const;

/**
 * Backend liveness, polled while the tab is open.
 *
 * Retries only on kinds where a retry could plausibly succeed. A 503 from an
 * unbuilt index does not fix itself, so retrying it three times just delays
 * telling the user what is actually wrong.
 */
export function useHealth() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 30_000,
    staleTime: 10_000,
    retry: (failureCount, error) =>
      error instanceof ApiError && error.retryable && failureCount < 2,
  });
}
