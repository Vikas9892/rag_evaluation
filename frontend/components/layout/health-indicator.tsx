"use client";

import { ApiError } from "@/services/api-error";
import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

/**
 * Backend status in the top bar.
 *
 * Four distinct states, because "not healthy" is not one situation: the API
 * being unreachable is a different problem from the API answering that its
 * pipeline is unavailable, and the user fixes them differently. While the first
 * request is in flight the status is unknown, and it says so rather than
 * guessing "healthy".
 */
export function HealthIndicator() {
  const { data, error, isPending } = useHealth();

  const state = resolveState({ data, error, isPending });

  return (
    <span
      className="border-border bg-muted/40 flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs"
      title={state.title}
    >
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full", state.dot)}
        data-testid="health-dot"
      />
      {/* The word carries the state, the dot only reinforces it — a status
          told in colour alone is no status at all. One node, not two: narrow
          screens hide it visually rather than removing it, so there is never a
          second live region announcing the same thing. */}
      <span className="text-muted-foreground sr-only sm:not-sr-only" role="status">
        {state.label}
      </span>
    </span>
  );
}

function resolveState({
  data,
  error,
  isPending,
}: {
  data?: { status: string };
  error: unknown;
  isPending: boolean;
}) {
  if (isPending) {
    return {
      label: "Checking…",
      dot: "bg-muted-foreground/40 animate-pulse",
      title: "Contacting the API",
    };
  }

  if (error) {
    const apiError = error instanceof ApiError ? error : null;
    if (apiError?.kind === "network" || apiError?.kind === "timeout") {
      return {
        label: "API unreachable",
        dot: "bg-destructive",
        title: apiError.userMessage,
      };
    }
    return {
      label: "Degraded",
      dot: "bg-warning",
      title: apiError?.userMessage ?? "The API responded with an error",
    };
  }

  if (data?.status === "healthy") {
    return { label: "API healthy", dot: "bg-success", title: "API is responding" };
  }

  // The endpoint answered with something other than "healthy" — report what it
  // said instead of translating it into a green light.
  return {
    label: data?.status ?? "Unknown",
    dot: "bg-warning",
    title: `API reported status: ${data?.status ?? "unknown"}`,
  };
}
