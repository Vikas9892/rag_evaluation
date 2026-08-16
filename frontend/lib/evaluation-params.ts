import type { RetrieverMode } from "@/types/api";

import { RETRIEVERS, TOP_K_DEFAULT, TOP_K_MAX, TOP_K_MIN } from "@/lib/query-params";

/** Which questions the table is showing. */
export const VIEWS = ["all", "missed", "worst"] as const;
export type EvaluationView = (typeof VIEWS)[number];

export const VIEW_DEFAULT: EvaluationView = "all";

/**
 * The Evaluation Lab's state, in the URL.
 *
 * Same reason as the query page: a run at top-5 dense and a run at top-10
 * hybrid are different measurements, and a result nobody can link to cannot be
 * cited in a discussion about which configuration to ship.
 */
export interface EvaluationParams {
  topK: number;
  retriever: RetrieverMode;
  view: EvaluationView;
}

/** The retriever the Evaluation Lab opens on. */
export const EVAL_RETRIEVER_DEFAULT: RetrieverMode = "dense";

export function parseEvaluationParams(params: URLSearchParams): EvaluationParams {
  return {
    topK: parseTopK(params.get("top_k")),
    retriever: parseRetriever(params.get("retriever")),
    view: parseView(params.get("view")),
  };
}

function parseView(raw: string | null): EvaluationView {
  return (VIEWS as readonly string[]).includes(raw ?? "")
    ? (raw as EvaluationView)
    : VIEW_DEFAULT;
}

function parseRetriever(raw: string | null): RetrieverMode {
  return (RETRIEVERS as readonly string[]).includes(raw ?? "")
    ? (raw as RetrieverMode)
    : EVAL_RETRIEVER_DEFAULT;
}

function parseTopK(raw: string | null): number {
  if (raw === null || !/^\d+$/.test(raw.trim())) return TOP_K_DEFAULT;
  const value = Number(raw.trim());
  return Math.min(TOP_K_MAX, Math.max(TOP_K_MIN, value));
}

export function buildEvaluationQuery({
  topK,
  retriever,
  view,
}: EvaluationParams): string {
  const params = new URLSearchParams();
  if (topK !== TOP_K_DEFAULT) params.set("top_k", String(topK));
  if (retriever !== EVAL_RETRIEVER_DEFAULT) params.set("retriever", retriever);
  if (view !== VIEW_DEFAULT) params.set("view", view);
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
