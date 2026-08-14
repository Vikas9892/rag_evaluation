"use client";

import { OctagonAlertIcon } from "lucide-react";

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, type ApiErrorKind } from "@/services/api-error";

/**
 * How a failure is presented to the user.
 *
 * `showDetail` decides whether the server's own `detail` string reaches the
 * screen. It is true only where that string is written for a user and is
 * actionable — a 422's validation message, a 503's "index not built". It is
 * false for 5xx, where `detail` can carry internals that belong in a log and
 * not in a browser.
 */
interface Presentation {
  title: string;
  description: string;
  showDetail: boolean;
}

/**
 * One entry per kind, so adding a kind to the taxonomy fails to compile until
 * someone decides what the user should be told about it.
 *
 * `cancelled` maps to null rather than to copy: an aborted request is not a
 * failure — the caller navigated away or superseded the query — and rendering
 * it as one would report a bug every time the user changed their mind.
 */
const PRESENTATION: Record<ApiErrorKind, Presentation | null> = {
  cancelled: null,
  network: {
    title: "Can't reach the API",
    description: "The request never left the browser, or the API isn't running.",
    showDetail: false,
  },
  timeout: {
    title: "The API took too long",
    description: "No response arrived within the deadline.",
    showDetail: false,
  },
  bad_request: {
    title: "That request wasn't valid",
    description: "The API rejected it as malformed.",
    showDetail: true,
  },
  not_found: {
    title: "Not found",
    description: "The API has nothing at that address.",
    showDetail: true,
  },
  rate_limited: {
    title: "Too many requests",
    description: "The API is rate limiting. Waiting a moment usually clears it.",
    showDetail: false,
  },
  unavailable: {
    title: "The API isn't ready",
    description:
      "The pipeline is unavailable — usually an unbuilt index or an unset GROQ_API_KEY.",
    showDetail: true,
  },
  server: {
    title: "The API failed",
    description: "Something broke on the server.",
    showDetail: false,
  },
  parse: {
    title: "Unexpected response",
    description: "The API returned a body this app doesn't understand.",
    showDetail: false,
  },
};

const UNEXPECTED: Presentation = {
  title: "Something went wrong",
  description: "An unexpected error occurred.",
  showDetail: false,
};

/**
 * The inline failure surface for an expected error — one that arrived as data.
 *
 * This is not an error boundary and must not be confused with one. A boundary
 * catches exceptions thrown during render and unmounts the subtree; a rejected
 * request never reaches it, and unmounting would take the retry button with it.
 * A failed query is data, so it renders here, in place, with the page intact.
 */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  if (!error) return null;

  const apiError = error instanceof ApiError ? error : null;
  const presentation = apiError ? PRESENTATION[apiError.kind] : UNEXPECTED;
  if (!presentation) return null;

  const detail = presentation.showDetail ? apiError?.detail : undefined;
  // Retry is offered only where it could work. Offering it on a 503 invites the
  // user to click at an unbuilt index until they give up.
  const canRetry = Boolean(onRetry) && (apiError ? apiError.retryable : true);

  return (
    <Alert variant="destructive" className={className}>
      <OctagonAlertIcon aria-hidden />
      <AlertTitle>{presentation.title}</AlertTitle>
      <AlertDescription>
        {presentation.description}
        {detail ? (
          <span className="mt-1 block font-mono text-xs break-words">{detail}</span>
        ) : null}
      </AlertDescription>
      {canRetry ? (
        <AlertAction>
          <Button size="sm" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </AlertAction>
      ) : null}
    </Alert>
  );
}
