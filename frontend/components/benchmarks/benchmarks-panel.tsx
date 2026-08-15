"use client";

import { ErrorState } from "@/components/error-state";
import { ms, ratio } from "@/components/metric-tile";
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
import { cn } from "@/lib/utils";
import type { BenchmarkCell, BenchmarkResponse } from "@/types/api";

const label = (cell: BenchmarkCell) =>
  `${cell.retriever} · top-${cell.top_k}${cell.reranker ? " · reranked" : ""}`;

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
          <span className="text-sm">{label(cell)}</span>
          <span className="bg-muted h-3 overflow-hidden rounded-sm" aria-hidden>
            <span
              className="bg-foreground/70 block h-full rounded-sm"
              // MRR is already a 0–1 proportion, so the bar is the value — no
              // rescaling to the maximum, which would exaggerate small gaps.
              style={{ width: `${Math.max(cell.metrics.mrr, 0) * 100}%` }}
            />
          </span>
          <span className="text-right font-mono text-sm">{ratio(cell.metrics.mrr)}</span>
        </li>
      ))}
    </ul>
  );
}

function Matrix({ data, best }: { data: BenchmarkResponse; best?: BenchmarkCell }) {
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
            <TableHead>Retriever</TableHead>
            <TableHead className="w-16">K</TableHead>
            <TableHead className="w-24">Rerank</TableHead>
            <TableHead className="w-28">Precision@K</TableHead>
            <TableHead className="w-24">Recall</TableHead>
            <TableHead className="w-24">MRR</TableHead>
            <TableHead className="w-24">Hit rate</TableHead>
            <TableHead className="w-28">Latency</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.cells.map((cell) => {
            const isBest = best && label(cell) === label(best);
            return (
              <TableRow key={label(cell)}>
                <TableCell className={cn(isBest && "font-medium")}>
                  {cell.retriever}
                  {isBest ? (
                    <span className="text-muted-foreground ml-2 text-xs">best MRR</span>
                  ) : null}
                </TableCell>
                <TableCell className="font-mono text-sm">{cell.top_k}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {cell.reranker ? "on" : "off"}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {ratio(cell.metrics.precision_at_k)}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {ratio(cell.metrics.recall_at_k)}
                </TableCell>
                <TableCell className={cn("font-mono text-sm", isBest && "font-medium")}>
                  {ratio(cell.metrics.mrr)}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {ratio(cell.metrics.hit_rate)}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {ms(cell.metrics.avg_latency_ms)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
