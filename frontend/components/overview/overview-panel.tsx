"use client";

import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";

import { ErrorState } from "@/components/error-state";
import { Modes } from "@/components/overview/modes";
import { Section } from "@/components/ui/section";
import { Stat, ms } from "@/components/ui/stat";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig, useDeepHealth } from "@/hooks/use-platform";
import { useMetrics } from "@/hooks/use-metrics";
import { ROUTES } from "@/lib/routes";
import type { HealthCheck } from "@/types/api";

/**
 * What this deployment is and whether it is working.
 *
 * Everything here is read from the API rather than written into the page. A
 * hardcoded "19 chunks" would be right until the index was rebuilt and wrong
 * silently thereafter, which is the failure this platform exists to catch in
 * other people's systems.
 *
 * Laid out as sections rather than a stack of cards: only the two mode panels
 * are objects you choose between. Status rows, metrics and links are content,
 * and framing each group would put four borders on screen that mean nothing.
 */
export function OverviewPanel() {
  const health = useDeepHealth();
  const config = useConfig();
  const metrics = useMetrics();

  return (
    <div className="flex flex-col gap-8">
      {/*
        First, because it is the only thing on this page that answers "what is
        this and what do I do with it". The health checks below matter to
        whoever runs the deployment; they are not the product.
      */}
      <Modes />

      <Section
        title="System status"
        description="Checked against the running deployment, not assumed."
      >
        {health.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : health.error ? (
          <ErrorState error={health.error} onRetry={() => void health.refetch()} />
        ) : (
          <ul className="border-border divide-border divide-y rounded-lg border">
            {health.data?.checks.map((check) => (
              <CheckRow key={check.name} check={check} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Corpus" description="What the benchmark index currently holds.">
        {config.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : config.error ? (
          <ErrorState error={config.error} onRetry={() => void config.refetch()} />
        ) : config.data ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Indexed chunks"
              value={config.data.indexed_chunks.toLocaleString()}
            />
            <Stat label="Documents" value={config.data.documents} />
            <Stat
              label="Chunk size"
              value={config.data.chunk_size}
              caption={`${config.data.chunk_overlap} character overlap`}
            />
            <Stat
              label="Embedding"
              value={
                <span className="text-[13px] break-all">
                  {config.data.embedding_model}
                </span>
              }
              caption="Every vector was produced by this model."
            />
          </div>
        ) : null}
      </Section>

      <Section
        title="Since cold start"
        description="Counted in this process and reset on restart — there is no persistence behind them."
      >
        {metrics.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : metrics.error ? (
          <ErrorState error={metrics.error} onRetry={() => void metrics.refetch()} />
        ) : metrics.data ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Queries" value={metrics.data.total_queries} />
              <Stat
                label="Errors"
                value={metrics.data.errors}
                tone={metrics.data.errors > 0 ? "danger" : undefined}
              />
              <Stat label="Avg retrieval" value={ms(metrics.data.avg_retrieval_ms)} />
              <Stat label="Avg generation" value={ms(metrics.data.avg_generation_ms)} />
            </div>
            <p className="text-subtle-foreground text-xs">
              The same numbers are scrapeable at{" "}
              <code className="font-mono">/metrics/prometheus</code>.
            </p>
          </>
        ) : null}
      </Section>

      <Section title="Quick actions" description="Where to go next.">
        <nav aria-label="Sections" className="grid gap-2 sm:grid-cols-2">
          {ROUTES.filter((r) => !["/", "/about"].includes(r.href)).map((route) => {
            const Icon = route.icon;
            return (
              <Link
                key={route.href}
                href={route.href}
                className="group border-border bg-card hover:border-border-strong hover:bg-accent focus-visible:ring-ring flex items-start gap-3 rounded-lg border p-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <Icon
                  aria-hidden
                  className="text-muted-foreground group-hover:text-foreground mt-0.5 size-4 shrink-0 transition-colors"
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    {route.label}
                    <ArrowRightIcon
                      aria-hidden
                      className="text-muted-foreground size-3 opacity-0 transition-opacity group-hover:opacity-100"
                    />
                  </span>
                  <span className="text-muted-foreground mt-0.5 block text-xs leading-snug">
                    {route.description}
                  </span>
                </span>
              </Link>
            );
          })}
        </nav>
      </Section>
    </div>
  );
}

const CHECK_TONE: Record<string, StatusTone> = {
  pass: "success",
  warn: "warning",
  fail: "danger",
};

function CheckRow({ check }: { check: HealthCheck }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-sm">
      <span className="min-w-[7rem] font-mono text-[13px]">{check.name}</span>
      {/* The word carries the state, not the tint: colour alone is unreadable
          to a screen reader and disappears under forced colours. */}
      <StatusBadge tone={CHECK_TONE[check.status] ?? "neutral"}>
        {check.status.toUpperCase()}
      </StatusBadge>
      <span className="text-muted-foreground min-w-0 flex-1 text-[13px]">
        {check.detail}
      </span>
    </li>
  );
}
