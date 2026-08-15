"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { MessageCircleQuestionIcon } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { QuestionInput } from "@/components/query/question-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineField } from "@/components/ui/inline-field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuestionHistory } from "@/hooks/use-question-history";
import { useRagQuery, type RagAnswer } from "@/hooks/use-rag-query";
import type { RetrieverMode, StreamDone } from "@/types/api";
import {
  buildQueryString,
  parseQueryParams,
  RETRIEVERS,
  TOP_K_MAX,
  TOP_K_MIN,
} from "@/lib/query-params";
import { NativeSelect } from "@/components/ui/native-select";
import { CopyButton } from "@/components/copy-button";
import { CorpusSelect } from "@/components/query/corpus-select";
import { RetrievalTable } from "@/components/query/retrieval-table";
import { PipelineDiagram } from "@/components/query/pipeline-diagram";

/**
 * The query surface.
 *
 * State lives in the URL, not in this component: the question and the retrieval
 * settings that produced an answer travel with the link, so a result can be
 * cited. That is the difference between this and a chat box.
 */
export function QueryPanel() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { q, topK, retriever, reranker, corpus } = parseQueryParams(
    new URLSearchParams(searchParams.toString()),
  );

  const { history, remember, forget } = useQuestionHistory();
  const { data, error, isFetching, refetch } = useRagQuery(
    q,
    topK,
    retriever,
    reranker,
    corpus,
  );

  function ask(question: string) {
    remember(question);
    // push, not replace: each question asked is a place the user can come back
    // to with the browser's Back button.
    router.push(
      `${pathname}${buildQueryString({ q: question, topK, retriever, reranker, corpus })}`,
    );
  }

  function changeSetting(
    next: Partial<{
      topK: number;
      retriever: RetrieverMode;
      reranker: boolean;
      corpus: string;
    }>,
  ) {
    // replace, not push: adjusting a setting is not a destination, and pushing
    // would make Back walk through every intermediate value.
    router.replace(
      `${pathname}${buildQueryString({ q, topK, retriever, reranker, corpus, ...next })}`,
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <QuestionInput
          // Remounts when the URL question changes so the draft follows a Back
          // or a shared link instead of holding the previous text.
          key={q}
          defaultValue={q}
          suggestions={history}
          isPending={isFetching}
          onSubmit={ask}
        />

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {/*
            First, because it changes what every other control operates on:
            the retriever and top-K are settings, but the corpus is the subject.
          */}
          <CorpusSelect
            value={corpus}
            onChange={(next) => changeSetting({ corpus: next })}
          />

          <TopKField value={topK} onCommit={(next) => changeSetting({ topK: next })} />

          <InlineField htmlFor="retriever" label="Retriever">
            <NativeSelect
              id="retriever"
              value={retriever}
              onChange={(event) =>
                changeSetting({ retriever: event.target.value as RetrieverMode })
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

          <label className="text-muted-foreground flex shrink-0 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={reranker}
              onChange={(event) => changeSetting({ reranker: event.target.checked })}
              className="size-4"
            />
            {/*
              Off by default and labelled with its cost, because it lifts MRR by
              ~0.04 and adds hundreds of milliseconds against a generation step
              of 300-600 ms — a trade worth making deliberately.
            */}
            Rerank <span className="text-xs">(slower, more accurate)</span>
          </label>

          {history.length > 0 ? (
            <Button type="button" variant="ghost" size="sm" onClick={forget}>
              Clear history
            </Button>
          ) : null}
        </div>
      </div>

      <Result
        question={q}
        isFetching={isFetching}
        error={error}
        data={data}
        requestedRetriever={retriever}
        onRetry={() => void refetch()}
      />
    </div>
  );
}

/**
 * How many chunks to retrieve.
 *
 * The typed value is held locally and committed on blur or Enter rather than on
 * every keystroke. Committing per keystroke means typing "12" first commits
 * "1" — a navigation, a refetch and a Groq call for a number the user was in
 * the middle of typing — and clearing the box commits the clamped minimum.
 */
function TopKField({
  value,
  onCommit,
}: {
  value: number;
  onCommit: (next: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const [committed, setCommitted] = useState(value);

  // Follow the URL when it changes from elsewhere: Back, or a shared link.
  // Adjusted during render rather than in an effect — React re-runs this
  // component before touching the DOM, so the box never paints a stale number.
  // A `key` would reset it too, but would also drop focus on every commit.
  if (value !== committed) {
    setCommitted(value);
    setDraft(String(value));
  }

  function commit() {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || draft.trim() === "") {
      setDraft(String(value));
      return;
    }
    const clamped = Math.min(TOP_K_MAX, Math.max(TOP_K_MIN, Math.round(parsed)));
    setDraft(String(clamped));
    if (clamped !== value) onCommit(clamped);
  }

  return (
    <InlineField htmlFor="top-k" label="Chunks retrieved">
      <Input
        id="top-k"
        type="number"
        inputMode="numeric"
        min={TOP_K_MIN}
        max={TOP_K_MAX}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          commit();
        }}
        className="w-20"
      />
    </InlineField>
  );
}

function Result({
  question,
  isFetching,
  error,
  data,
  requestedRetriever,
  onRetry,
}: {
  question: string;
  isFetching: boolean;
  error: unknown;
  data?: RagAnswer;
  requestedRetriever: RetrieverMode;
  onRetry: () => void;
}) {
  if (!question) {
    return (
      <EmptyState
        icon={MessageCircleQuestionIcon}
        title="No question yet"
        description="Ask something above. The question and settings are kept in the URL, so an answer can be linked to."
      />
    );
  }

  const partial = data?.answer ?? "";

  // A failure with nothing on screen is the whole story. A failure after tokens
  // arrived is not: the user is mid-read, and replacing what they have with an
  // error throws away the part that worked.
  if (error && !partial) return <ErrorState error={error} onRetry={onRetry} />;

  if (!partial && !data?.complete) {
    if (!isFetching) return null;
    return (
      <Card aria-busy>
        <CardHeader>
          <CardTitle>Answer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {/* Shaped like the paragraph it is replacing, so nothing jumps when
              the first tokens arrive. */}
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </CardContent>
      </Card>
    );
  }

  const streaming = isFetching && !data?.complete && !error;

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle>Answer</CardTitle>
          {/*
            Offered only once the answer is whole. Copying mid-stream hands over
            half a sentence that looks like the whole one.
          */}
          {data?.complete ? <CopyButton value={partial} label="Copy answer" /> : null}
        </CardHeader>
        <CardContent className="space-y-3">
          {/*
            aria-live is polite and on a container that exists from the start:
            announcing every token would make the answer unreadable with a
            screen reader, so the region is only read once it settles.
          */}
          <p
            className="leading-relaxed whitespace-pre-wrap"
            aria-live="polite"
            aria-busy={streaming}
          >
            {partial}
            {streaming ? (
              <span
                aria-hidden
                className="bg-foreground ml-0.5 inline-block h-4 w-1.5 animate-pulse align-text-bottom"
              />
            ) : null}
          </p>

          {data?.metrics?.abstained ? <Abstained /> : null}
          {data?.metrics ? <Metrics metrics={data.metrics} /> : null}
        </CardContent>
      </Card>

      {/* Kept below the answer, not instead of it. */}
      {error ? <ErrorState error={error} onRetry={onRetry} /> : null}

      {data && data.sources.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Retrieval</CardTitle>
          </CardHeader>
          <CardContent>
            <RetrievalTable
              sources={data.sources}
              // The echo from the server is authoritative; the requested value
              // stands in until `done` arrives, since sources render first.
              retriever={data.metrics?.retriever ?? requestedRetriever}
            />
          </CardContent>
        </Card>
      ) : null}

      {data?.metrics?.pipeline?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <PipelineDiagram stages={data.metrics.pipeline} />
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

/**
 * The model declined, and that is a result rather than a failure.
 *
 * Reported by the server, which checks the answer against the exact reply the
 * system prompt demands. Retrieval may still have been fine — the chunks below
 * show whether the answer was there to find — so this says what happened
 * without assigning blame to a stage.
 */
function Abstained() {
  return (
    <p className="border-muted-foreground/30 text-muted-foreground border-l-2 pl-3 text-sm">
      The model declined to answer from the retrieved context. Compare the chunks below:
      if the answer is there, the retrieval was right and the generation was not.
    </p>
  );
}

function Metrics({ metrics }: { metrics: StreamDone }) {
  return (
    <p className="text-muted-foreground text-xs">
      {Math.round(metrics.total_latency_ms)} ms total
      {metrics.first_token_latency_ms !== null
        ? ` · ${Math.round(metrics.first_token_latency_ms)} ms to first token`
        : null}{" "}
      · request {metrics.request_id.slice(0, 8)}
    </p>
  );
}
