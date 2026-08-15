"use client";

import Link from "next/link";

import { ErrorState } from "@/components/error-state";
import { MetricTile, ms } from "@/components/metric-tile";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig, useDeepHealth } from "@/hooks/use-platform";
import { useMetrics } from "@/hooks/use-metrics";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { HealthCheck } from "@/types/api";

/**
 * What this deployment is and whether it is working.
 *
 * Everything here is read from the API rather than written into the page. A
 * hardcoded "19 chunks" would be right until the index was rebuilt and wrong
 * silently thereafter, which is the failure this platform exists to catch in
 * other people's systems.
 */
export function OverviewPanel() {
  const health = useDeepHealth();
  const config = useConfig();
  const metrics = useMetrics();

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Dependencies</CardTitle>
        </CardHeader>
        <CardContent>
          {health.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : health.error ? (
            <ErrorState error={health.error} onRetry={() => void health.refetch()} />
          ) : (
            <ul className="space-y-2">
              {health.data?.checks.map((check) => (
                <CheckRow key={check.name} check={check} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Corpus</CardTitle>
        </CardHeader>
        <CardContent>
          {config.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : config.error ? (
            <ErrorState error={config.error} onRetry={() => void config.refetch()} />
          ) : config.data ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <MetricTile
                label="Indexed chunks"
                value={String(config.data.indexed_chunks)}
              />
              <MetricTile label="Documents" value={String(config.data.documents)} />
              <MetricTile
                label="Chunk size"
                value={`${config.data.chunk_size}`}
                caption={`${config.data.chunk_overlap} character overlap`}
              />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Since cold start</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : metrics.error ? (
            <ErrorState error={metrics.error} onRetry={() => void metrics.refetch()} />
          ) : metrics.data ? (
            <div className="grid gap-3 sm:grid-cols-4">
              <MetricTile label="Queries" value={String(metrics.data.total_queries)} />
              <MetricTile label="Errors" value={String(metrics.data.errors)} />
              <MetricTile
                label="Avg retrieval"
                value={ms(metrics.data.avg_retrieval_ms)}
              />
              <MetricTile
                label="Avg generation"
                value={ms(metrics.data.avg_generation_ms)}
              />
            </div>
          ) : null}
          <p className="text-muted-foreground mt-3 text-xs">
            Counted in this process and reset on restart — there is no persistence behind
            them. The same numbers are scrapeable at <code>/metrics/prometheus</code>.
          </p>
        </CardContent>
      </Card>

      <nav aria-label="Sections" className="grid gap-3 sm:grid-cols-2">
        {ROUTES.filter((r) => r.href !== "/" && r.href !== "/about").map((route) => {
          const Icon = route.icon;
          return (
            <Link
              key={route.href}
              href={route.href}
              className="border-border hover:bg-accent focus-visible:ring-ring rounded-lg border p-4 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="flex items-center gap-2 font-medium">
                <Icon aria-hidden className="size-4" />
                {route.label}
              </span>
              <span className="text-muted-foreground mt-1 block text-sm">
                {route.description}
              </span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

function CheckRow({ check }: { check: HealthCheck }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
      {/* The word carries the state, not the dot: colour alone is unreadable to
          a screen reader and disappears under forced colours. */}
      <span
        aria-hidden
        className={cn(
          "size-2 shrink-0 translate-y-[-1px] rounded-full",
          check.status === "pass" && "bg-emerald-500",
          check.status === "warn" && "bg-amber-500",
          check.status === "fail" && "bg-red-500",
        )}
      />
      <span className="font-medium">{check.name}</span>
      <span className="text-muted-foreground text-xs uppercase">{check.status}</span>
      <span className="text-muted-foreground">— {check.detail}</span>
    </li>
  );
}
