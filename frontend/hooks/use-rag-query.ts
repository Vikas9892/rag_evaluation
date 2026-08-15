"use client";

import { useQuery } from "@tanstack/react-query";

import { postQuery } from "@/services/api";

/**
 * The answer for a question, keyed on the question and its retrieval settings.
 *
 * A query rather than the mutation ADR 008 sketched. The URL owns the question,
 * so a shared link must produce its answer on arrival; with a mutation that
 * means an effect firing a request on mount, which is the pattern react-query
 * exists to remove. Keying on `[question, topK]` gets it declaratively.
 *
 * Caching matters here beyond speed: every call spends Groq budget, so an
 * identical question answered a moment ago should not be paid for twice.
 * `enabled` keeps it from firing on an empty question — the state the page is
 * in before anything has been asked.
 */
export function ragQueryKey(question: string, topK: number) {
  return ["rag-query", question, topK] as const;
}

export function useRagQuery(question: string, topK: number) {
  return useQuery({
    queryKey: ragQueryKey(question, topK),
    queryFn: ({ signal }) => postQuery(question, topK, signal),
    enabled: question.trim().length > 0,
    // An answer for a given question and top-K does not change unless the index
    // is rebuilt, so re-asking within a session should be free.
    staleTime: 5 * 60_000,
  });
}
