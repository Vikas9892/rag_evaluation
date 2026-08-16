"use client";

import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig, useEvaluation } from "@/hooks/use-platform";

/**
 * The measured numbers, read from the API rather than typed here.
 *
 * They used to be a hardcoded list, and by the time anyone noticed they claimed
 * Recall 1.00 and MRR 1.00 against a 15-question dataset that had since grown
 * to 53 — on a page whose own next section argues that a fabricated metric is
 * the thing this product exists to avoid. A number that cannot go stale is the
 * only kind worth putting on this page.
 */
export function MeasuredQuality() {
  // Dense at top-5: the shipped default, so this reports what a user gets
  // rather than the best configuration in the matrix.
  const evaluation = useEvaluation(5, "dense");
  const config = useConfig();

  if (evaluation.error) {
    return (
      <ErrorState error={evaluation.error} onRetry={() => void evaluation.refetch()} />
    );
  }

  if (evaluation.isPending || !evaluation.data) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  const m = evaluation.data.metrics;
  const tiles = [
    { label: "Recall@5", value: m.recall_at_k.toFixed(3) },
    { label: "MRR", value: m.mrr.toFixed(3) },
    { label: "Precision@5", value: m.precision_at_k.toFixed(3) },
    { label: "Retrieval p50", value: `${Math.round(m.p50_latency_ms)} ms` },
  ];

  return (
    <>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="border-border rounded-lg border p-3">
            <dt className="text-muted-foreground text-xs">{tile.label}</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">{tile.value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-muted-foreground mt-3">
        Measured just now over {evaluation.data.dataset_size} labelled questions
        {config.data ? ` against ${config.data.indexed_chunks} chunks` : null}, with dense
        retrieval at top-5 — the shipped default. Precision@5 is structurally capped near{" "}
        {(1 / evaluation.data.top_k).toFixed(2)} here, because most questions have one
        relevant chunk and five are retrieved; read Recall and MRR instead. A dataset this
        size measures the corpus as much as the retriever.
      </p>
    </>
  );
}
