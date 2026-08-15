"use client";

import Link from "next/link";

import { ErrorState } from "@/components/error-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig } from "@/hooks/use-platform";

/**
 * What this deployment is configured with.
 *
 * Read-only, and deliberately so. The settings that change a *result* — the
 * question, top-K, the retriever — live in the URL on the query page, because
 * an answer is only citable if the settings that produced it travel with the
 * link. Moving them here would put them in a place a link cannot carry.
 *
 * Everything below is fetched. A page that listed the model name from a
 * TypeScript constant would be describing the frontend's belief about the
 * deployment rather than the deployment.
 */
export function SettingsPanel() {
  const { data, error, isPending, refetch } = useConfig();

  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />;
  if (isPending) return <Skeleton className="h-96 w-full" />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-dashed p-4">
        <p className="text-sm font-medium">Retrieval settings live with the query</p>
        <p className="text-muted-foreground mt-1 text-sm">
          Top-K and the retriever are chosen on the{" "}
          <Link href="/query" className="underline underline-offset-4">
            query page
          </Link>{" "}
          and kept in the URL, so a result can be linked to and reproduced. This page
          shows what the deployment itself is running.
        </p>
      </div>

      <Section title="Retrieval">
        <Row label="Retrievers available" value={data.retrievers.join(", ")} />
        <Row label="Default top-K" value={String(data.default_top_k)} />
        <Row
          label="Cross-encoder reranker"
          value={data.reranker_enabled ? "enabled" : "implemented, not in the live path"}
          note={
            data.reranker_enabled
              ? undefined
              : "The pipeline trace reports it skipped rather than pretending it ran."
          }
        />
      </Section>

      <Section title="Embedding and chunking">
        <Row label="Embedding model" value={data.embedding_model} />
        <Row label="Chunk size" value={`${data.chunk_size} characters`} />
        <Row label="Chunk overlap" value={`${data.chunk_overlap} characters`} />
        <Row
          label="Minimum chunk"
          value={`${data.min_chunk_chars} characters`}
          note="Shorter chunks are merged into a neighbour; splitting on headings otherwise emits heading-only chunks that match a query's wording while carrying none of the answer."
        />
        <Row
          label="Indexed chunks"
          value={`${data.indexed_chunks} from ${data.documents} documents`}
        />
      </Section>

      <Section title="Generation">
        <Row label="Model" value={data.llm_model} />
        <Row
          label="Temperature"
          value={String(data.llm_temperature)}
          note={
            data.llm_temperature === 0
              ? "Zero, so the same question and context give the same answer — a benchmark that moved on its own would measure nothing."
              : undefined
          }
        />
        <Row label="Max tokens" value={String(data.llm_max_tokens)} />
        <Row label="Context chunks" value={String(data.max_context_chunks)} />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="divide-border divide-y">{children}</dl>
      </CardContent>
    </Card>
  );
}

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[14rem_1fr] sm:gap-4">
      <dt className="text-muted-foreground text-sm">{label}</dt>
      <dd>
        <span className="font-mono text-sm">{value}</span>
        {note ? (
          <p className="text-muted-foreground mt-1 text-xs leading-snug">{note}</p>
        ) : null}
      </dd>
    </div>
  );
}
