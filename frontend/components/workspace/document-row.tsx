"use client";

import { CheckIcon, FileTextIcon, Loader2Icon, Trash2Icon, XIcon } from "lucide-react";
import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";
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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

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
    <li className="border-border rounded-lg border p-4">
      <div className="flex flex-wrap items-start gap-3">
        <FileTextIcon
          aria-hidden
          className="text-muted-foreground mt-0.5 size-4 shrink-0"
        />

        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{document.filename}</p>
          <p className="text-muted-foreground mt-0.5 text-xs">
            {formatSize(document.size_bytes)}
            {ready ? ` · ${document.chunk_count} chunks` : null}
            {` · ${document.corpus_id}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={document.status} />
          {ready ? (
            // A link, styled as a button: this navigates, and a <button> that
            // navigates loses middle-click, open-in-new-tab and the status bar.
            <Link
              href={`/query?corpus=${encodeURIComponent(corpusId)}`}
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              Ask questions
            </Link>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete ${document.filename}`}
            disabled={deleting}
            onClick={() => onDelete(document.document_id)}
          >
            <Trash2Icon aria-hidden />
          </Button>
        </div>
      </div>

      {/*
        The stage list is shown only while work is happening. Leaving six ticks
        on every finished document turns the list into noise.
      */}
      {!ready && !failed ? <Stages status={document.status} /> : null}

      {failed ? (
        <p className="text-destructive mt-3 text-sm" role="alert">
          {document.error ?? "Indexing failed."}
        </p>
      ) : null}
    </li>
  );
}

function Stages({ status }: { status: DocumentStatus }) {
  const currentIndex = STAGES.findIndex((s) => s.status === status);

  return (
    <ol className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
      {STAGES.map((stage, index) => {
        const done = index < currentIndex;
        const active = index === currentIndex;
        return (
          <li
            key={stage.status}
            className={cn(
              "flex items-center gap-1.5 text-xs",
              done && "text-muted-foreground",
              active && "text-foreground font-medium",
              !done && !active && "text-muted-foreground/50",
            )}
          >
            {done ? (
              <CheckIcon aria-hidden className="size-3" />
            ) : active ? (
              <Loader2Icon aria-hidden className="size-3 animate-spin" />
            ) : (
              <span
                aria-hidden
                className="border-muted-foreground/40 size-3 rounded-full border"
              />
            )}
            {stage.label}
          </li>
        );
      })}
    </ol>
  );
}

function StatusBadge({ status }: { status: DocumentStatus }) {
  const ready = status === "READY";
  const failed = status === "FAILED";

  return (
    <span
      className={cn(
        "rounded-md border px-2 py-0.5 font-mono text-xs",
        ready && "border-emerald-600/30 text-emerald-700 dark:text-emerald-400",
        failed && "border-destructive/40 text-destructive",
        !ready && !failed && "text-muted-foreground",
      )}
    >
      {/* The word is the status; the colour only reinforces it, so this stays
          readable in forced colours and to a screen reader. */}
      {failed ? <XIcon aria-hidden className="mr-1 inline size-3" /> : null}
      {status}
    </span>
  );
}
