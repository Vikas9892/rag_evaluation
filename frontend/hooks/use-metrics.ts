"use client";

import { useQuery } from "@tanstack/react-query";

import { getMetrics } from "@/services/api";

/**
 * In-process counters, polled while the overview is open.
 *
 * Shorter interval than the config it sits beside, because these change with
 * every query while the rest of the deployment does not.
 */
export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: ({ signal }) => getMetrics(signal),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
