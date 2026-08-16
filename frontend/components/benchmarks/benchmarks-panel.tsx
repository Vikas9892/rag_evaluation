"use client";

import { ArrowUpIcon } from "lucide-react";
import { useState } from "react";

import { ErrorState } from "@/components/error-state";
import { ms, ratio } from "@/components/ui/stat";
import { StatusBadge } from "@/components/ui/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useBenchmarks } from "@/hooks/use-platform";
import {
  configurationLabel as label,
  nextSort,
  recommend,
  sortCells,
  type Sort,
  type SortKey,
} from "@/lib/benchmark-table";
import { cn } from "@/lib/utils";
import type { BenchmarkCell, BenchmarkResponse } from "@/types/api";

/**
 * Every retriever at every top-K, measured on the same questions.
 *
 * This is the surface the platform is named for: not "does retrieval work" but
 * "which configuration works better, and by how much".
 */
export function BenchmarksPanel() {
  const { data, error, isPending, refetch } = useBenchmarks();

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }
  if (!data) return null;

  const ranked = [...data.cells].sort((a, b) => b.metrics.mrr - a.metrics.mrr);

  return (
    <div className="space-y-6">
      {data.pending > 0 ? (
        <div className="rounded-lg border border-dashed p-4">
          <p className="text-sm font-medium">
            Measuring — {data.cells.length} of {data.cells.length + data.pending}{" "}
            configurations done
          </p>
          <p className="text-muted-foreground mt-1 text-sm">
            A cold sweep takes minutes, mostly in the reranker. The results below fill in
            as they are measured; nothing here is estimated.
          </p>
        </div>
      ) : null}

      <Verdict data={data} ranked={ranked} />

      <Recommendation data={data} />

      <Card>
        <CardHeader>
          <CardTitle>MRR by configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <MrrChart ranked={ranked} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Full matrix</CardTitle>
        </CardHeader>
        <CardContent>
          <Matrix data={data} best={ranked[0]} />
        </CardContent>
      </Card>
    </div>
  );
}

function Verdict({ data, ranked }: { data: BenchmarkResponse; ranked: BenchmarkCell[] }) {
  // A partial matrix has nothing to conclude from yet, and saying so beats
  // announcing a winner that the remaining cells might beat.
  if (data.pending > 0) return null;

  if (!data.discriminating) {
    return (
      <div className="rounded-lg border border-dashed p-4">
        <p className="text-sm font-medium">Every configuration scored the same</p>
        <p className="text-muted-foreground mt-1 text-sm">
          The matrix is measuring the corpus, not the retrievers. At {data.dataset_size}{" "}
          questions there is not enough signal to separate them, and presenting this as a
          comparison would be a claim the data does not support.
        </p>
      </div>
    );
  }

  const best = ranked[0];
  const worst = ranked[ranked.length - 1];

  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm">
        <strong className="font-medium">{label(best)}</strong> ranks the first relevant
        chunk highest, at MRR {ratio(best.metrics.mrr)} against {ratio(worst.metrics.mrr)}{" "}
        for {label(worst)}.
      </p>
      <p className="text-muted-foreground mt-1 text-sm">
        Measured over {data.dataset_size} labelled questions. A difference this size on a
        dataset this small is a direction to investigate, not a settled result.
      </p>
    </div>
  );
}

/**
 * Which configuration to ship, and what the choice costs.
 *
 * The highest MRR is not automatically the answer. Reranking wins on quality
 * and costs hundreds of milliseconds against a generation step of 300-600 ms,
 * so this names two configurations — the best outright, and the cheapest one
 * that is not meaningfully worse — and states the trade between them rather
 * than crowning a winner and leaving the cost unmentioned.
 */
function Recommendation({ data }: { data: BenchmarkResponse }) {
  // Recommending from a partial sweep would mean revising the recommendation
  // as the remaining cells land.
  if (data.pending > 0 || !data.discriminating) return null;

  const rec = recommend(data.cells);
  if (!rec) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommended configuration</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {rec.agreed ? (
          <p>
            <strong className="font-medium">{label(rec.best)}</strong> is both the most
            accurate and the cheapest of the configurations within{" "}
            {rec.tolerance.toFixed(2)} MRR of the best, so there is no trade to make here.
          </p>
        ) : (
          <>
            <p>
              Ship <strong className="font-medium">{label(rec.value)}</strong>. It is the
              fastest configuration within {rec.tolerance.toFixed(2)} MRR of the best, at{" "}
              {ms(rec.value.metrics.avg_latency_ms)} per query.
            </p>
            <p className="text-muted-foreground">
              {label(rec.best)} scores {ratio(rec.best.metrics.mrr)} against{" "}
              {ratio(rec.value.metrics.mrr)} — {rec.extraMrr.toFixed(3)} more MRR for{" "}
              {ms(rec.extraLatencyMs)} more per query. Worth it when a wrong answer is
              expensive; not worth it in an interactive box.
            </p>
          </>
        )}
        <p className="text-muted-foreground text-xs">
          The {rec.tolerance.toFixed(2)} MRR band is a judgement, not a significance test:
          on {data.dataset_size} questions, one moving from rank 2 to rank 1 shifts MRR by
          about 0.009, so smaller gaps are read as noise.
        </p>
      </CardContent>
    </Card>
  );
}

/**
 * One series, one unit, one axis.
 *
 * A bar chart is legitimate here in a way it was not for the retrieval trace:
 * every value is an MRR in [0, 1], so the lengths are comparable and no colour
 * has to carry identity — the row label does. The design system's chart ramp is
 * achromatic and fails the palette validator as a categorical palette, which is
 * exactly why nothing here is encoded by hue.
 */
function MrrChart({ ranked }: { ranked: BenchmarkCell[] }) {
  return (
    <ul className="space-y-1.5">
      {ranked.map((cell) => (
        <li
          key={label(cell)}
          className="grid grid-cols-[10rem_1fr_3.5rem] items-center gap-2"
        >
          <span className="truncate text-[13px]">{label(cell)}</span>
          <span className="bg-muted h-2 overflow-hidden rounded-full" aria-hidden>
            <span
              // MRR is indigo everywhere in this product, so a reader who
              // learns the mapping once does not relearn it per page.
              className="bg-chart-3 block h-full rounded-full"
              // MRR is already a 0–1 proportion, so the bar is the value — no
              // rescaling to the maximum, which would exaggerate small gaps.
              style={{ width: `${Math.max(cell.metrics.mrr, 0) * 100}%` }}
            />
          </span>
          <span className="text-right font-mono text-[13px] tabular-nums">
            {ratio(cell.metrics.mrr)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The sortable columns, and what each header says. */
const COLUMNS: {
  key: SortKey;
  label: string;
  className?: string;
  /** Right-aligned, tabular. Text columns stay left. */
  numeric?: boolean;
}[] = [
  { key: "configuration", label: "Retriever" },
  { key: "top_k", numeric: true, label: "K", className: "w-16" },
  { key: "precision_at_k", numeric: true, label: "Precision@K", className: "w-28" },
  { key: "recall_at_k", numeric: true, label: "Recall", className: "w-24" },
  { key: "mrr", numeric: true, label: "MRR", className: "w-24" },
  { key: "hit_rate", numeric: true, label: "Hit rate", className: "w-24" },
  { key: "avg_latency_ms", numeric: true, label: "Latency", className: "w-28" },
];

function Matrix({ data, best }: { data: BenchmarkResponse; best?: BenchmarkCell }) {
  // Opens on MRR descending: the matrix exists to answer "which is best", and
  // the API's own order is the sweep order, which answers nothing.
  const [sort, setSort] = useState<Sort>({ key: "mrr", direction: "desc" });
  const rows = sortCells(data.cells, sort);

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableCaption className="text-left">
          {data.cells.length} configurations over {data.dataset_size} labelled questions.
          Precision@K falls as K rises by construction — more retrieved chunks divide the
          same relevant ones — so read Recall and MRR when comparing across K.
        </TableCaption>
        <TableHeader>
          <TableRow>
            {COLUMNS.map((column) => (
              <TableHead
                key={column.key}
                className={cn(column.className, column.numeric && "text-right")}
                // Announced to a screen reader, which otherwise has no way to
                // know the table is sorted or by what.
                aria-sort={
                  sort.key === column.key
                    ? sort.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                }
              >
                <button
                  type="button"
                  onClick={() => setSort((current) => nextSort(current, column.key))}
                  className={cn(
                    "hover:text-foreground flex items-center gap-1",
                    column.numeric && "ml-auto flex-row-reverse",
                  )}
                >
                  {column.label}
                  {sort.key === column.key ? (
                    <ArrowUpIcon
                      aria-hidden
                      className={cn(
                        "size-3 transition-transform",
                        sort.direction === "desc" && "rotate-180",
                      )}
                    />
                  ) : null}
                </button>
              </TableHead>
            ))}
            <TableHead className="w-24">Rerank</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((cell) => {
            const isBest = best && label(cell) === label(best);
            return (
              <TableRow key={label(cell)}>
                <TableCell className={cn(isBest && "font-medium")}>
                  {cell.retriever}
                  {isBest ? (
                    <StatusBadge tone="success" className="ml-2">
                      best MRR
                    </StatusBadge>
                  ) : null}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {cell.top_k}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {ratio(cell.metrics.precision_at_k)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {ratio(cell.metrics.recall_at_k)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono text-sm tabular-nums",
                    isBest && "text-foreground font-medium",
                  )}
                >
                  {ratio(cell.metrics.mrr)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm tabular-nums">
                  {ratio(cell.metrics.hit_rate)}
                </TableCell>
                <TableCell className="text-muted-foreground text-right font-mono text-xs tabular-nums">
                  {ms(cell.metrics.avg_latency_ms)}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {cell.reranker ? "on" : "off"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
