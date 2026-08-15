import { ChevronRightIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { PipelineStage, StageName } from "@/types/api";

const STAGE_LABEL: Record<StageName, string> = {
  embedding: "Embedding",
  dense: "Dense",
  sparse: "BM25",
  fusion: "Fusion",
  reranker: "Reranker",
  generation: "Generation",
};

const STAGE_DETAIL: Record<StageName, string> = {
  embedding: "The question becomes a vector",
  dense: "Vector similarity over the index",
  sparse: "Keyword matching over the corpus",
  fusion: "Reciprocal rank fusion of both rankings",
  reranker: "Cross-encoder re-scoring",
  generation: "The LLM writes the answer",
};

/**
 * What the pipeline actually did, stage by stage.
 *
 * Every stage is drawn every time, including the ones that did not run: a stage
 * that disappeared from the picture would read as "this deployment has no
 * reranker" rather than "the reranker did not run for this query". A skipped
 * stage is marked in words and by a dashed outline, never by colour alone, and
 * carries no timing — its zero is an absence, not a fast measurement.
 *
 * There is no chart here, and that is a decision rather than an omission. The
 * design system's chart ramp is achromatic (`oklch(L 0 0)`), and running it
 * through the palette validator fails on the chroma floor and on the
 * normal-vision floor — adjacent steps sit at ΔE 6.7, well under the 15 needed
 * to tell segments apart with full colour vision. A stacked bar would encode
 * six identities in shades nobody can reliably separate, so identity lives in
 * labels and magnitude in numbers, with one sentence naming where the time
 * actually went.
 */
export function PipelineDiagram({ stages }: { stages: readonly PipelineStage[] }) {
  const ran = stages.filter((stage) => stage.status === "ok");
  const total = ran.reduce((sum, stage) => sum + stage.latency_ms, 0);

  return (
    <div className="space-y-3">
      <ol className="flex flex-wrap items-stretch gap-1">
        {stages.map((stage, index) => (
          <li key={stage.name} className="flex items-stretch gap-1">
            <Stage stage={stage} total={total} />
            {index < stages.length - 1 ? (
              <ChevronRightIcon
                aria-hidden
                className="text-muted-foreground/50 size-4 shrink-0 self-center"
              />
            ) : null}
          </li>
        ))}
      </ol>
      <Summary ran={ran} total={total} />
    </div>
  );
}

function Stage({ stage, total }: { stage: PipelineStage; total: number }) {
  const skipped = stage.status === "skipped";
  const failed = stage.status === "error";

  return (
    <div
      className={cn(
        "min-w-28 rounded-lg border px-2.5 py-2",
        skipped && "border-dashed opacity-60",
        failed && "border-destructive",
      )}
      title={STAGE_DETAIL[stage.name]}
    >
      <div className="text-sm font-medium">{STAGE_LABEL[stage.name]}</div>

      {skipped ? (
        // In words, not just in styling: dashed-and-faded is not readable as
        // "did not run" on its own, and is invisible in forced-colours mode.
        <div className="text-muted-foreground text-xs">did not run</div>
      ) : (
        <>
          <div className="text-muted-foreground font-mono text-xs">
            {formatLatency(stage.latency_ms)}
            {total > 0 ? (
              <span className="ml-1">
                ({Math.round((stage.latency_ms / total) * 100)}%)
              </span>
            ) : null}
          </div>
          <Candidates stage={stage} />
        </>
      )}

      {failed ? <div className="text-destructive text-xs">failed</div> : null}
    </div>
  );
}

function Candidates({ stage }: { stage: PipelineStage }) {
  const { candidates_in: from, candidates_out: to } = stage;
  // Null where the notion does not apply — a question is not a candidate set,
  // and generation emits prose rather than a shortlist.
  if (from == null && to == null) return null;

  return (
    <div className="text-muted-foreground/80 font-mono text-xs">
      {from ?? "—"} <span aria-hidden>→</span>
      <span className="sr-only">to</span> {to ?? "—"}
    </div>
  );
}

function Summary({ ran, total }: { ran: readonly PipelineStage[]; total: number }) {
  if (!ran.length || total <= 0) return null;

  const dominant = ran.reduce((a, b) => (b.latency_ms > a.latency_ms ? b : a));
  const share = Math.round((dominant.latency_ms / total) * 100);

  return (
    <p className="text-muted-foreground text-xs">
      {formatLatency(total)} across {ran.length} stage{ran.length === 1 ? "" : "s"} —{" "}
      <strong className="font-medium">{STAGE_LABEL[dominant.name]}</strong> accounted for{" "}
      {share}% of it.
    </p>
  );
}

function formatLatency(ms: number): string {
  // Sub-millisecond stages are real: fusion runs in ~0.05 ms, and rounding it
  // to "0 ms" would suggest it did not happen.
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 100) return `${ms.toFixed(1)} ms`;
  return `${Math.round(ms)} ms`;
}
