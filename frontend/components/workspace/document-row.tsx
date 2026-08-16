"use client";

import { CheckIcon, FileTextIcon, Loader2Icon, Trash2Icon, XIcon } from "lucide-react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import type { DocumentResponse, DocumentStatus } from "@/types/api";

/** The worker's stages, in order, as the UI walks through them. */
const STAGES: { status: DocumentStatus; label: string }[] = [
  { status: "UPLOADING", label: "Uploaded" },
  { status: "QUEUED", label: "Queued" },
  { status: "PARSING", label: "Parsed" },
  { status: "CHUNKING", label: "Chunked" },
  { status: "EMBEDDING", label: "Embedded" },
  { status: "INDEXING", label: "Indexed" },
];

/** The worker's stages in pipeline order, so the breakdown reads as a sequence. */
const TIMED_STAGES: { key: string; label: string }[] = [
  { key: "parse", label: "parse" },
  { key: "chunk", label: "chunk" },
  { key: "embed", label: "embed" },
  { key: "index", label: "index" },
];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

const STATUS_TONE: Record<string, StatusTone> = {
  READY: "success",
  FAILED: "danger",
};

/**
 * One document, as a table row.
 *
 * A row rather than a card: a knowledge base is a list of comparable things,
 * and framing each one separately makes scanning ten of them harder than
 * scanning ten rows.
 */
export function DocumentRow({
  document,
  corpusId,
  onDelete,
  deleting = false,
}: {
  document: DocumentResponse;
  corpusId: string;
  onDelete: (documentId: string) => void;
  deleting?: boolean;
}) {
  const failed = document.status === "FAILED";
  const ready = document.status === "READY";

  return (
    <tr className="border-border hover:bg-muted/30 border-b transition-colors last:border-b-0">
      <td className="py-2.5 pr-3 pl-3 align-top">
        <div className="flex items-start gap-2.5">
          <FileTextIcon
            aria-hidden
            className="text-subtle-foreground mt-0.5 size-3.5 shrink-0"
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{document.filename}</div>

            {/* The stage list is shown only while work is happening. Six ticks
                on every finished document is noise. */}
            {!ready && !failed ? <Stages status={document.status} /> : null}

            {ready && document.timings_ms ? (
              <Timings timings={document.timings_ms} />
            ) : null}

            {failed ? (
              <p className="text-destructive mt-1 text-xs" role="alert">
                {document.error ?? "Indexing failed."}
              </p>
            ) : null}
          </div>
        </div>
      </td>

      <td className="text-muted-foreground py-2.5 pr-3 text-right align-top font-mono text-xs whitespace-nowrap tabular-nums">
        {formatSize(document.size_bytes)}
      </td>

      <td className="text-muted-foreground py-2.5 pr-3 text-right align-top font-mono text-xs whitespace-nowrap tabular-nums">
        {ready ? document.chunk_count : "—"}
      </td>

      <td className="py-2.5 pr-3 align-top">
        <StatusBadge tone={STATUS_TONE[document.status] ?? "neutral"}>
          {failed ? <XIcon aria-hidden className="size-3" /> : null}
          {document.status}
        </StatusBadge>
      </td>

      <td className="py-2.5 pr-3 align-top">
        <div className="flex items-center justify-end gap-1">
          {ready ? (
            // A link styled as a button: this navigates, and a <button> that
            // navigates loses middle-click and open-in-new-tab.
            <Link
              href={`/query?corpus=${encodeURIComponent(corpusId)}`}
              className={buttonVariants({ variant: "outline", size: "xs" })}
            >
              Ask questions
            </Link>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Delete ${document.filename}`}
            disabled={deleting}
            onClick={() => onDelete(document.document_id)}
          >
            <Trash2Icon aria-hidden />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function Timings({ timings }: { timings: Record<string, number> }) {
  const stages = TIMED_STAGES.filter(({ key }) => typeof timings[key] === "number");
  if (stages.length === 0) return null;

  const total = stages.reduce((sum, { key }) => sum + timings[key], 0);

  return (
    <p className="text-subtle-foreground mt-1 font-mono text-[11px]">
      <span className="text-muted-foreground">Indexed in {formatMs(total)}</span>
      {" — "}
      {stages.map(({ key, label }, index) => (
        <span key={key}>
          {index > 0 ? " · " : null}
          {label} {formatMs(timings[key])}
        </span>
      ))}
    </p>
  );
}

function Stages({ status }: { status: DocumentStatus }) {
  const currentIndex = STAGES.findIndex((s) => s.status === status);

  return (
    <ol className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
      {STAGES.map((stage, index) => {
        const done = index < currentIndex;
        const active = index === currentIndex;
        return (
          <li
            key={stage.status}
            className={cn(
              "flex items-center gap-1 text-[11px]",
              done && "text-muted-foreground",
              active && "text-foreground font-medium",
              !done && !active && "text-subtle-foreground/50",
            )}
          >
            {done ? (
              <CheckIcon aria-hidden className="text-success size-3" />
            ) : active ? (
              <Loader2Icon aria-hidden className="text-primary size-3 animate-spin" />
            ) : (
              <span
                aria-hidden
                className="border-border-strong size-2 rounded-full border"
              />
            )}
            {stage.label}
          </li>
        );
      })}
    </ol>
  );
}
