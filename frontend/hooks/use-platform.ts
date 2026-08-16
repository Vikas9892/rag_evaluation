"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getBenchmarks,
  getConfig,
  getDeepHealth,
  getEvaluation,
  getSettings,
} from "@/services/api";
import type { RetrieverMode } from "@/types/api";

/**
 * Pipeline configuration — models, chunking, corpus size.
 *
 * Long stale time because none of it changes without a redeploy or an index
 * rebuild, and re-fetching it on every page would be asking the server to
 * repeat itself.
 */
export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: ({ signal }) => getConfig(signal),
    staleTime: 30 * 60_000,
  });
}

/**
 * Every setting, grouped, with when it takes effect.
 *
 * Distinct from useConfig: /config reports the values, /settings reports what
 * each one *is* — query-time or indexing-time, and whether changing it
 * invalidates the index. The UI must not restate that taxonomy from memory,
 * because it would then be the frontend's opinion rather than the API's.
 */
export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: ({ signal }) => getSettings(signal),
    staleTime: 30 * 60_000,
  });
}

/** Dependency-by-dependency health, polled less often than the liveness probe. */
export function useDeepHealth() {
  return useQuery({
    queryKey: ["health", "deep"],
    queryFn: ({ signal }) => getDeepHealth(signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useEvaluation(topK: number, retriever: RetrieverMode) {
  return useQuery({
    queryKey: ["evaluation", topK, retriever],
    queryFn: ({ signal }) => getEvaluation(topK, retriever, signal),
    // The API caches these itself, so a revisit is instant; this just avoids
    // asking again within a session.
    staleTime: 10 * 60_000,
  });
}

export function useBenchmarks() {
  return useQuery({
    queryKey: ["benchmarks"],
    queryFn: ({ signal }) => getBenchmarks(signal),
    staleTime: 10 * 60_000,
    // The API measures a bounded number of configurations per call and reports
    // the rest as pending, because a full cold sweep takes minutes and a request
    // that long does not survive a proxy. Polling continues the run.
    refetchInterval: (query) => (query.state.data?.pending ? 2_000 : false),
  });
}
