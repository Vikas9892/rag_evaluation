"use client";

import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineField } from "@/components/ui/inline-field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentRow } from "@/components/workspace/document-row";
import { UploadDropzone } from "@/components/workspace/upload-dropzone";
import {
  useDeleteDocument,
  useDocuments,
  useQueueStatus,
  useUploadDocument,
} from "@/hooks/use-documents";
import { FileTextIcon } from "lucide-react";

/** Uploads land here rather than in the benchmark corpus, which is built offline. */
const WORKSPACE_CORPUS = "workspace";

/**
 * Upload documents, watch them index, then query them.
 *
 * The corpus is fixed rather than free text: the benchmark corpus must stay
 * untouched, and letting someone type its name would be the one way to
 * invalidate a published metric from the UI.
 */
export function WorkspacePanel() {
  const [chunkSize, setChunkSize] = useState<string>("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const documents = useDocuments(WORKSPACE_CORPUS);
  const queue = useQueueStatus();
  const upload = useUploadDocument(WORKSPACE_CORPUS);
  const remove = useDeleteDocument(WORKSPACE_CORPUS);

  function handleFiles(files: File[]) {
    const parsed = Number(chunkSize);
    const size = Number.isFinite(parsed) && parsed >= 50 ? parsed : undefined;
    // Sequential rather than parallel: the worker indexes one at a time
    // anyway, and a burst of large uploads would just queue in the browser.
    for (const file of files) {
      upload.mutate({ file, chunkSize: size });
    }
  }

  const list = documents.data?.documents ?? [];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add documents</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <UploadDropzone onFiles={handleFiles} disabled={upload.isPending} />

          {upload.error ? (
            <ErrorState error={upload.error} onRetry={() => upload.reset()} />
          ) : null}

          <div>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4"
              aria-expanded={showAdvanced}
              onClick={() => setShowAdvanced((open) => !open)}
            >
              {showAdvanced ? "Hide" : "Show"} indexing settings
            </button>

            {showAdvanced ? (
              <div className="mt-3 space-y-2">
                <InlineField htmlFor="chunk-size" label="Chunk size">
                  <Input
                    id="chunk-size"
                    type="number"
                    min={50}
                    max={4000}
                    placeholder="250"
                    value={chunkSize}
                    onChange={(event) => setChunkSize(event.target.value)}
                    className="w-24"
                  />
                </InlineField>
                {/*
                  Stated plainly because the alternative is a user changing this
                  and wondering why their existing documents did not change.
                */}
                <p className="text-muted-foreground text-xs">
                  Applies to documents uploaded from now on. Chunk size is fixed when a
                  document is indexed — changing it does not re-chunk anything already
                  here, which would need those documents re-uploaded.
                </p>
              </div>
            ) : null}
          </div>

          {/*
            Said before an upload, not after one goes missing. On a host with an
            ephemeral filesystem — a free Hugging Face Space, say — the container
            is replaced and everything written to it goes with it. The benchmark
            corpus is unaffected: it is baked into the image.
          */}
          {queue.data?.storage_ephemeral ? (
            <p
              role="status"
              className="border-border text-muted-foreground border-t pt-3 text-xs"
            >
              <strong className="text-foreground">
                Uploads on this deployment are temporary.
              </strong>{" "}
              Its storage does not survive a restart, so documents you add here are lost
              when the server is replaced. The benchmark corpus behind Evaluation and
              Benchmarks is part of the image and stays.
            </p>
          ) : null}

          {queue.data && !queue.data.durable ? (
            <p className="text-muted-foreground border-border border-t pt-3 text-xs">
              Indexing runs on an in-process worker. Jobs are recovered if the API
              restarts, but they are not queued durably — set <code>REDIS_URL</code> for
              that.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your knowledge base</CardTitle>
        </CardHeader>
        <CardContent>
          {documents.isPending ? (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : documents.error ? (
            <ErrorState
              error={documents.error}
              onRetry={() => void documents.refetch()}
            />
          ) : list.length === 0 ? (
            <EmptyState
              icon={FileTextIcon}
              title="No documents yet"
              description="Upload a PDF, text or Markdown file above. It is parsed, chunked, embedded and indexed on a worker — the page keeps working while that happens."
            />
          ) : (
            // Horizontally scrollable rather than reflowed: these columns are
            // narrow already, and a card-per-document on mobile would lose the
            // alignment that makes a knowledge base scannable.
            // No negative margin here. Bleeding the scroller to the card's
            // edges with -mx-4 widened it past the parent's content box, and
            // the page itself then scrolled sideways by 255px at 390px wide —
            // the scroll container has to sit inside its parent to contain
            // anything.
            <div className="overflow-x-auto">
              {/* The 640px floor waits for lg, because the sidebar returns at
                  md and leaves ~544px of content — narrower than the floor,
                  which put 125px of sideways scroll on the page at 768px.
                  Below lg the columns simply compress; table-fixed is what
                  makes that safe. */}
              <table className="w-full table-fixed border-collapse text-left lg:min-w-[640px]">
                <thead>
                  <tr className="border-border text-subtle-foreground border-b text-[11px] tracking-wider uppercase">
                    {/* table-fixed: column widths come from these headers
                        rather than from the content, so a long filename cannot
                        widen the table past its container. Without it the
                        table's intrinsic minimum let the whole page be dragged
                        sideways on a phone. */}
                    <th scope="col" className="py-2 pr-3 pl-3 font-medium">
                      Document
                    </th>
                    <th scope="col" className="w-16 py-2 pr-3 text-right font-medium">
                      Size
                    </th>
                    <th scope="col" className="w-16 py-2 pr-3 text-right font-medium">
                      Chunks
                    </th>
                    <th scope="col" className="w-24 py-2 pr-3 font-medium">
                      Status
                    </th>
                    <th scope="col" className="w-36 py-2 pr-3 text-right font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((document) => (
                    <DocumentRow
                      key={document.document_id}
                      document={document}
                      corpusId={WORKSPACE_CORPUS}
                      deleting={remove.isPending}
                      onDelete={(id) => remove.mutate(id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {remove.error ? (
            <div className="mt-3">
              <ErrorState error={remove.error} onRetry={() => remove.reset()} />
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
