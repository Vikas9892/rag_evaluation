"use client";

import { useQuery } from "@tanstack/react-query";

import { streamQuery } from "@/services/api";
import { ApiError } from "@/services/api-error";
import type { RetrieverMode, StreamDone, StreamSource } from "@/types/api";

/**
 * An answer as it accumulates, plus whatever the stream has told us so far.
 *
 * `complete` is not derivable from having text: a stream that dies half way
 * through also leaves text behind. Only the `done` event means the answer is
 * whole, and presenting a truncated one as finished is the failure this flag
 * exists to prevent.
 */
export interface RagAnswer {
  answer: string;
  sources: StreamSource[];
  complete: boolean;
  metrics: StreamDone | null;
}

const EMPTY: RagAnswer = { answer: "", sources: [], complete: false, metrics: null };

export function ragQueryKey(
  question: string,
  topK: number,
  retriever: RetrieverMode,
  reranker: boolean,
) {
  // The retriever is part of the identity of an answer, not a detail of how it
  // was fetched: the same question under dense and under hybrid are two
  // different results, and sharing a cache entry would show one as the other.
  return ["rag-query", question, topK, retriever, reranker] as const;
}

/**
 * Stream the answer for a question, keyed on the question and its settings.
 *
 * Still a react-query query, so Milestone 8's properties survive: a shared link
 * produces its answer on arrival, and an identical question already answered is
 * served from cache rather than paid for again. Partial answers are published
 * through `setQueryData` as tokens arrive, which is how a single cache entry can
 * also be a live one.
 *
 * The signal comes from react-query, so navigating away aborts the request
 * mid-stream instead of leaving the connection reading into a dead component.
 */
export function useRagQuery(
  question: string,
  topK: number,
  retriever: RetrieverMode,
  reranker: boolean,
) {
  return useQuery<RagAnswer>({
    queryKey: ragQueryKey(question, topK, retriever, reranker),
    queryFn: async ({ signal, client, queryKey }) => {
      let current: RagAnswer = EMPTY;

      const publish = (next: Partial<RagAnswer>) => {
        current = { ...current, ...next };
        // Makes the in-flight answer visible without waiting for the promise to
        // settle. react-query replaces this with the returned value at the end.
        client.setQueryData(queryKey, current);
      };

      publish({});

      for await (const event of streamQuery(
        question,
        topK,
        signal,
        retriever,
        reranker,
      )) {
        switch (event.type) {
          case "sources":
            publish({ sources: event.data });
            break;
          case "token":
            publish({ answer: current.answer + event.data });
            break;
          case "done":
            publish({ complete: true, metrics: event.data });
            break;
          case "error":
            // The server reports a failure it hit part-way through. Throwing
            // keeps the tokens already published — react-query holds the last
            // data alongside the error — so the user keeps a partial answer and
            // is told why it stopped.
            throw new ApiError("server", event.data, { detail: event.data });
        }
      }

      if (!current.complete) {
        // The connection ended without a 'done'. Something truncated it, and
        // silently treating that as success would present half an answer as
        // the whole one.
        throw new ApiError("parse", "The answer stream ended before it finished", {
          detail: "The connection closed before the answer was complete.",
        });
      }

      return current;
    },
    enabled: question.trim().length > 0,
    // An answer for a given question and top-K does not change unless the index
    // is rebuilt, so re-asking within a session should be free.
    staleTime: 5 * 60_000,
  });
}
