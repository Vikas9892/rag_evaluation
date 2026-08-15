"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { MessageCircleQuestionIcon } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PendingPanel } from "@/components/pending-panel";
import { QuestionInput } from "@/components/query/question-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuestionHistory } from "@/hooks/use-question-history";
import { useRagQuery } from "@/hooks/use-rag-query";
import {
  buildQueryString,
  parseQueryParams,
  TOP_K_MAX,
  TOP_K_MIN,
} from "@/lib/query-params";

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
  const { q, topK } = parseQueryParams(new URLSearchParams(searchParams.toString()));

  const { history, remember, forget } = useQuestionHistory();
  const { data, error, isFetching, refetch } = useRagQuery(q, topK);

  function ask(question: string) {
    remember(question);
    // push, not replace: each question asked is a place the user can come back
    // to with the browser's Back button.
    router.push(`${pathname}${buildQueryString({ q: question, topK })}`);
  }

  function changeTopK(next: number) {
    // replace, not push: adjusting a setting is not a destination, and pushing
    // would make Back walk through every intermediate value.
    router.replace(`${pathname}${buildQueryString({ q, topK: next })}`);
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

        <div className="flex flex-wrap items-center gap-4">
          <TopKField value={topK} onCommit={changeTopK} />

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
    <Field className="flex-row items-center gap-2">
      <FieldLabel htmlFor="top-k" className="text-muted-foreground text-sm">
        Chunks retrieved
      </FieldLabel>
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
    </Field>
  );
}

function Result({
  question,
  isFetching,
  error,
  data,
  onRetry,
}: {
  question: string;
  isFetching: boolean;
  error: unknown;
  data?: { answer: string; total_latency_ms: number; request_id: string };
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

  // Errors outrank the loading state: while react-query retries a failure,
  // isFetching is true again, and showing a skeleton would hide the reason the
  // first attempt failed.
  if (error) return <ErrorState error={error} onRetry={onRetry} />;

  if (isFetching && !data) {
    return (
      <Card aria-busy>
        <CardHeader>
          <CardTitle>Answer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {/* Shaped like the paragraph it is replacing, so nothing jumps when
              the real answer arrives. */}
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Answer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="leading-relaxed whitespace-pre-wrap">{data.answer}</p>
          <p className="text-muted-foreground text-xs">
            {Math.round(data.total_latency_ms)} ms · request {data.request_id.slice(0, 8)}
          </p>
        </CardContent>
      </Card>

      <PendingPanel milestone="Milestones 10–11">
        Confidence, per-source attribution and the retrieval trace. The trace needs
        per-stage scores the API does not expose yet: <code>HybridRetriever</code> fuses
        dense and sparse into one number and discards the component ranks.
      </PendingPanel>
    </>
  );
}
