"use client";

import { CheckIcon, XIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ErrorState } from "@/components/error-state";
import { MetricTile, ms, ratio } from "@/components/metric-tile";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineField } from "@/components/ui/inline-field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEvaluation } from "@/hooks/use-platform";
import {
  buildEvaluationQuery,
  parseEvaluationParams,
  VIEWS,
  type EvaluationView,
} from "@/lib/evaluation-params";
import { RETRIEVERS, TOP_K_MAX, TOP_K_MIN } from "@/lib/query-params";
import type { EvaluationResponse, PerQuestionResult, RetrieverMode } from "@/types/api";

const VIEW_LABEL: Record<EvaluationView, string> = {
  all: "All questions",
  missed: "Missed only",
  worst: "Worst ranked first",
};

/**
 * Retrieval quality over the labelled dataset.
 *
 * These metrics live here and not beside an ad-hoc question because they are
 * undefined without ground truth. That separation is the product's central
 * design decision, not a layout choice.
 *
 * The run is configurable because a single number at one top-K is not an
 * evaluation, it is an anecdote. Changing K or the retriever re-runs against
 * the same labelled dataset, and the settings live in the URL so a result can
 * be linked to rather than described.
 */
export function EvaluationPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { topK, retriever, view } = parseEvaluationParams(
    new URLSearchParams(searchParams.toString()),
  );

  const { data, error, isPending, isFetching, refetch } = useEvaluation(topK, retriever);

  function change(
    next: Partial<{ topK: number; retriever: RetrieverMode; view: EvaluationView }>,
  ) {
    // replace, not push: adjusting the run is not a destination, and Back
    // should leave the page rather than walk every intermediate setting.
    router.replace(
      `${pathname}${buildEvaluationQuery({ topK, retriever, view, ...next })}`,
    );
  }

  return (
    <div className="space-y-6">
      <RunControls
        topK={topK}
        retriever={retriever}
        view={view}
        running={isFetching}
        onChange={change}
      />

      {error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : isPending ? (
        <Pending />
      ) : data ? (
        <>
          <Metrics data={data} />
          <Failures data={data} onShowMissed={() => change({ view: "missed" })} />
          <Card>
            <CardHeader>
              <CardTitle>Per question</CardTitle>
            </CardHeader>
            <CardContent>
              <PerQuestion data={data} view={view} />
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function RunControls({
  topK,
  retriever,
  view,
  running,
  onChange,
}: {
  topK: number;
  retriever: RetrieverMode;
  view: EvaluationView;
  running: boolean;
  onChange: (
    next: Partial<{ topK: number; retriever: RetrieverMode; view: EvaluationView }>,
  ) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <InlineField htmlFor="eval-top-k" label="Chunks retrieved">
        <Input
          id="eval-top-k"
          type="number"
          inputMode="numeric"
          min={TOP_K_MIN}
          max={TOP_K_MAX}
          defaultValue={topK}
          // Committed on blur or Enter, never per keystroke: every commit
          // re-runs retrieval over the whole labelled dataset, so typing "12"
          // would first run the whole thing at K=1.
          onBlur={(event) => commitTopK(event.target, topK, onChange)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            commitTopK(event.currentTarget, topK, onChange);
          }}
          className="w-20"
        />
      </InlineField>

      <InlineField htmlFor="eval-retriever" label="Retriever">
        <NativeSelect
          id="eval-retriever"
          value={retriever}
          onChange={(event) =>
            onChange({ retriever: event.target.value as RetrieverMode })
          }
          className="w-32"
        >
          {RETRIEVERS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </NativeSelect>
      </InlineField>

      <InlineField htmlFor="eval-view" label="Show">
        <NativeSelect
          id="eval-view"
          value={view}
          onChange={(event) => onChange({ view: event.target.value as EvaluationView })}
          className="w-48"
        >
          {VIEWS.map((option) => (
            <option key={option} value={option}>
              {VIEW_LABEL[option]}
            </option>
          ))}
        </NativeSelect>
      </InlineField>

      {running ? (
        <span className="text-muted-foreground text-xs" role="status">
          Running over the dataset…
        </span>
      ) : null}
    </div>
  );
}

function commitTopK(
  input: HTMLInputElement,
  current: number,
  onChange: (next: { topK: number }) => void,
) {
  const parsed = Number(input.value);
  if (!Number.isFinite(parsed) || input.value.trim() === "") {
    input.value = String(current);
    return;
  }
  const clamped = Math.min(TOP_K_MAX, Math.max(TOP_K_MIN, Math.round(parsed)));
  input.value = String(clamped);
  if (clamped !== current) onChange({ topK: clamped });
}

function Pending() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function Metrics({ data }: { data: EvaluationResponse }) {
  const m = data.metrics;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile
          label="Precision@K"
          value={ratio(m.precision_at_k)}
          // Without this the number reads as a failing grade. It is arithmetic.
          caption={`Capped near ${(1 / data.top_k).toFixed(2)} here: most questions have one relevant chunk and ${data.top_k} are retrieved.`}
        />
        <MetricTile
          label="Recall"
          value={ratio(m.recall_at_k)}
          caption="Share of the relevant chunks that were retrieved. The metric to read on this corpus."
        />
        <MetricTile
          label="MRR"
          value={ratio(m.mrr)}
          caption="How high the first relevant chunk ranks. 1.0 means always first."
        />
        <MetricTile
          label="Hit rate"
          value={ratio(m.hit_rate)}
          caption={`Questions with at least one relevant chunk in the top ${data.top_k}.`}
        />
      </div>

      {/*
        Latency is reported separately from quality because it is a different
        kind of claim: quality is a property of the index, latency is a property
        of this machine on this run.
      */}
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricTile
          label="Median latency"
          value={ms(m.p50_latency_ms)}
          caption="Retrieval only. Generation is not measured here."
        />
        <MetricTile
          label="p95 latency"
          value={ms(m.p95_latency_ms)}
          caption="The slowest 1 in 20. The mean hides this, and this is what a waiting user meets."
        />
        <MetricTile
          label="Mean latency"
          value={ms(m.avg_latency_ms)}
          caption="Kept for comparison with the tail above, not as the headline."
        />
      </div>
    </div>
  );
}

/**
 * The questions that failed, named.
 *
 * An average is a summary of the questions it hides. A hit rate of 0.96 over 53
 * questions is two failures, and those two are the only ones worth reading —
 * they are where the next improvement is.
 */
function Failures({
  data,
  onShowMissed,
}: {
  data: EvaluationResponse;
  onShowMissed: () => void;
}) {
  const missed = data.questions.filter((q) => !q.hit);

  if (missed.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Failures</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Every question retrieved at least one relevant chunk at top-{data.top_k}. That
            is a property of this dataset at this K, not a guarantee — lower K until it
            breaks to find the margin.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {missed.length} question{missed.length === 1 ? "" : "s"} retrieved nothing
          relevant
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="space-y-2">
          {missed.slice(0, 5).map((q) => (
            <li key={q.id} className="text-sm">
              <span className="text-muted-foreground mr-2 font-mono text-xs">
                #{q.id}
              </span>
              {q.question}
            </li>
          ))}
        </ul>
        {missed.length > 5 ? (
          <button
            type="button"
            onClick={onShowMissed}
            className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4"
          >
            Show all {missed.length} in the table
          </button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** The rows a view shows, in the order it shows them. */
function rowsFor(
  questions: readonly PerQuestionResult[],
  view: EvaluationView,
): PerQuestionResult[] {
  if (view === "missed") return questions.filter((q) => !q.hit);
  if (view === "worst") {
    // Ascending reciprocal rank: a miss is 0 and sorts first, then the
    // questions whose first relevant chunk ranked lowest. Copied before
    // sorting — sort mutates, and this array belongs to the query cache.
    return [...questions].sort((a, b) => a.reciprocal_rank - b.reciprocal_rank);
  }
  return [...questions];
}

function PerQuestion({ data, view }: { data: EvaluationResponse; view: EvaluationView }) {
  const rows = rowsFor(data.questions, view);

  if (rows.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No question missed at top-{data.top_k} with {data.retriever} retrieval.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableCaption className="text-left">
          {rows.length} of {data.dataset_size} labelled questions, {data.retriever}{" "}
          retrieval at top-{data.top_k}. Averages hide the questions that fail, which is
          what this table is for.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>Question</TableHead>
            <TableHead className="w-16">Hit</TableHead>
            <TableHead className="w-20">RR</TableHead>
            <TableHead className="w-24">Recall</TableHead>
            <TableHead className="w-24">Latency</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((q) => (
            <TableRow key={q.id}>
              <TableCell className="text-muted-foreground font-mono text-xs">
                {q.id}
              </TableCell>
              <TableCell className="max-w-md">{q.question}</TableCell>
              <TableCell>
                {q.hit ? (
                  <>
                    <CheckIcon aria-hidden className="size-4" />
                    <span className="sr-only">retrieved</span>
                  </>
                ) : (
                  <>
                    <XIcon aria-hidden className="text-destructive size-4" />
                    <span className="sr-only">missed</span>
                  </>
                )}
              </TableCell>
              <TableCell className="font-mono text-sm">
                {ratio(q.reciprocal_rank)}
              </TableCell>
              <TableCell className="font-mono text-sm">{ratio(q.recall)}</TableCell>
              <TableCell className="text-muted-foreground font-mono text-xs">
                {ms(q.latency_ms)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
