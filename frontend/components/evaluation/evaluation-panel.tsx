"use client";

import { CheckIcon, XIcon } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { MetricTile, ms, ratio } from "@/components/metric-tile";
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
import { useEvaluation } from "@/hooks/use-platform";
import type { EvaluationResponse } from "@/types/api";

/**
 * Retrieval quality over the labelled dataset.
 *
 * These metrics live here and not beside an ad-hoc question because they are
 * undefined without ground truth. That separation is the product's central
 * design decision, not a layout choice.
 */
export function EvaluationPanel({
  topK = 5,
  retriever = "hybrid",
}: {
  topK?: number;
  retriever?: "dense" | "sparse" | "hybrid";
}) {
  const { data, error, isPending, refetch } = useEvaluation(topK, retriever);

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (isPending) {
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
  if (!data) return null;

  return (
    <div className="space-y-6">
      <Metrics data={data} />
      <Card>
        <CardHeader>
          <CardTitle>Per question</CardTitle>
        </CardHeader>
        <CardContent>
          <PerQuestion data={data} />
        </CardContent>
      </Card>
    </div>
  );
}

function Metrics({ data }: { data: EvaluationResponse }) {
  const m = data.metrics;
  return (
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
  );
}

function PerQuestion({ data }: { data: EvaluationResponse }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableCaption className="text-left">
          {data.dataset_size} labelled questions, {data.retriever} retrieval at top-
          {data.top_k}. Averages hide the questions that fail, which is what this table is
          for.
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
          {data.questions.map((q) => (
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
