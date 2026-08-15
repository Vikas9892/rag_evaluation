"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { RetrieverMode, SourceInfo } from "@/types/api";

/** Which stage columns are meaningful for the strategy that ran. */
const COLUMNS: Record<RetrieverMode, readonly StageKey[]> = {
  hybrid: ["dense", "sparse", "fused"],
  dense: ["dense"],
  sparse: ["sparse"],
};

type StageKey = "dense" | "sparse" | "fused";

const STAGE_LABEL: Record<StageKey, string> = {
  dense: "Dense",
  sparse: "BM25",
  fused: "Fused",
};

const STAGE_UNITS: Record<StageKey, string> = {
  dense: "cosine similarity",
  sparse: "BM25 score",
  fused: "reciprocal rank fusion sum",
};

/**
 * What each retrieval stage thought of each chunk.
 *
 * The table leads with rank rather than score because ranks are the only part
 * that compares across stages. Dense scores are cosine similarities around 0.5,
 * BM25 scores are unbounded and often above 1, and an RRF sum is around 0.03 —
 * putting them on any shared scale, a bar or a heat colour, would assert a
 * comparison that does not exist. Scores are shown as plain text beside the
 * rank, in their own units, and never next to each other.
 *
 * Columns are limited to the stages the chosen strategy actually runs: a dense
 * query has no BM25 column at all, rather than a column of blanks that would
 * read as "BM25 found nothing".
 */
export function RetrievalTable({
  sources,
  retriever,
}: {
  sources: readonly SourceInfo[];
  retriever: RetrieverMode;
}) {
  const columns = COLUMNS[retriever];

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableCaption className="text-left">
          {sources.length} chunk{sources.length === 1 ? "" : "s"} retrieved by{" "}
          <strong>{retriever}</strong> retrieval.
          {retriever === "hybrid" ? (
            <>
              {" "}
              A dash means that retriever did not surface the chunk within its candidate
              window — not that it scored zero.
            </>
          ) : null}{" "}
          The cross-encoder reranker did not run, so no stage is shown for it.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>Chunk</TableHead>
            {columns.map((key) => (
              <TableHead key={key} className="w-32" title={STAGE_UNITS[key]}>
                {STAGE_LABEL[key]}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.map((source) => (
            <Row key={source.chunk_id} source={source} columns={columns} />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Row({ source, columns }: { source: SourceInfo; columns: readonly StageKey[] }) {
  const [expanded, setExpanded] = useState(false);
  const heading =
    typeof source.metadata?.heading === "string" ? source.metadata.heading : null;

  return (
    <TableRow>
      <TableCell className="text-muted-foreground align-top font-mono text-xs">
        {source.rank}
      </TableCell>
      <TableCell className="align-top">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{source.document_id}</span>
          {heading ? <Badge variant="secondary">{heading}</Badge> : null}
          <span className="text-muted-foreground font-mono text-xs">
            {source.chunk_id}
          </span>
        </div>
        <p
          className={cn(
            "text-muted-foreground mt-1 max-w-prose text-sm whitespace-pre-wrap",
            // Collapsed by default: a top-20 result set of full chunks buries
            // the ranking, which is what the table is for.
            !expanded && "line-clamp-2",
          )}
        >
          {source.text}
        </p>
        {source.text.length > 140 ? (
          <Button
            variant="link"
            size="xs"
            className="h-auto px-0"
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? "Show less" : "Show more"}
          </Button>
        ) : null}
      </TableCell>
      {columns.map((key) => (
        <TableCell key={key} className="align-top">
          <StageCell stage={source.scores?.[key] ?? null} label={STAGE_LABEL[key]} />
        </TableCell>
      ))}
    </TableRow>
  );
}

function StageCell({
  stage,
  label,
}: {
  stage: { score: number; rank: number } | null;
  label: string;
}) {
  if (!stage) {
    return (
      <span
        className="text-muted-foreground"
        title={`${label} did not retrieve this chunk`}
      >
        <span aria-hidden>—</span>
        <span className="sr-only">not retrieved by {label}</span>
      </span>
    );
  }

  return (
    <div className="leading-tight">
      <span className="font-mono text-sm">#{stage.rank}</span>
      {/* Secondary, and never aligned with another stage's score: the units
          differ, so a reader comparing them across columns is being misled. */}
      <span className="text-muted-foreground ml-2 font-mono text-xs">
        {formatScore(stage.score)}
      </span>
    </div>
  );
}

function formatScore(score: number): string {
  // RRF sums sit around 0.03 and cosine around 0.56; a fixed precision would
  // print either "0.03" or "0.560000" depending on which stage won the coin
  // toss. Significant digits keep both readable.
  return score >= 1 ? score.toFixed(2) : score.toPrecision(3);
}
