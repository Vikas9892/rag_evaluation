"use client";

import Link from "next/link";

import { ErrorState } from "@/components/error-state";
import { Section } from "@/components/ui/section";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useQueueStatus } from "@/hooks/use-documents";
import { useConfig, useDeepHealth, useSettings } from "@/hooks/use-platform";
import type { SettingDescriptor } from "@/types/api";

/** The order the groups read in: what you change most often, first. */
const GROUP_ORDER = ["retrieval", "generation", "indexing"] as const;

const GROUP_LABEL: Record<string, string> = {
  retrieval: "Retrieval",
  generation: "Generation",
  indexing: "Indexing",
};

const GROUP_HINT: Record<string, string> = {
  retrieval: "Chosen per request. Changing these affects only the next query.",
  generation: "How the answer is written once the chunks are chosen.",
  indexing:
    "Fixed when a document is indexed. Changing these invalidates every existing vector.",
};

/**
 * What this deployment is configured with, and when each setting takes effect.
 *
 * Read-only, and deliberately so. The settings that change a *result* — the
 * question, top-K, the retriever — live in the URL on the query page, because
 * an answer is only citable if the settings that produced it travel with the
 * link. Moving them here would put them somewhere a link cannot carry.
 *
 * The grouping and the "requires re-indexing" flags come from `/settings`
 * rather than being restated here. A page that decided for itself which
 * settings were indexing-time would be publishing the frontend's belief about
 * the pipeline instead of the pipeline's own answer.
 */
export function SettingsPanel() {
  const settings = useSettings();
  const config = useConfig();
  const queue = useQueueStatus();
  const health = useDeepHealth();

  if (settings.error) {
    return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  }
  if (settings.isPending) return <Skeleton className="h-96 w-full" />;
  if (!settings.data) return null;

  const groups = settings.data.groups;
  const ordered = [
    ...GROUP_ORDER.filter((key) => groups[key]),
    ...Object.keys(groups).filter(
      (key) => !GROUP_ORDER.includes(key as (typeof GROUP_ORDER)[number]),
    ),
  ];

  return (
    <div className="flex flex-col gap-8">
      <div className="border-border bg-card rounded-lg border border-dashed p-3.5">
        <p className="text-sm font-medium">Retrieval settings live with the query</p>
        <p className="text-muted-foreground mt-1 text-[13px] leading-snug">
          Top-K and the retriever are chosen on the{" "}
          <Link
            href="/query"
            className="text-info underline decoration-dotted underline-offset-4"
          >
            query page
          </Link>{" "}
          and kept in the URL, so a result can be linked to and reproduced. This page
          shows what the deployment itself is running.
        </p>
      </div>

      {ordered.map((key) => (
        <Section key={key} title={GROUP_LABEL[key] ?? key} description={GROUP_HINT[key]}>
          <div className="border-border divide-border divide-y rounded-lg border">
            {groups[key].map((setting) => (
              <SettingRow key={setting.key} setting={setting} />
            ))}
          </div>
        </Section>
      ))}

      <Section
        title="Infrastructure"
        description="How this deployment is running, reported by it rather than assumed."
      >
        <div className="border-border divide-border divide-y rounded-lg border">
          <InfraRow
            label="Indexing queue"
            value={queue.data ? queue.data.backend : "—"}
            note={queue.data?.note}
            badge={
              queue.data ? (
                <StatusBadge tone={queue.data.durable ? "success" : "warning"}>
                  {queue.data.durable ? "durable" : "not durable"}
                </StatusBadge>
              ) : null
            }
          />
          <InfraRow
            label="Storage"
            value={queue.data?.storage_ephemeral ? "ephemeral" : "persistent"}
            note={
              queue.data?.storage_ephemeral
                ? "Uploaded documents are lost when this server restarts. The benchmark corpus is built into the image and is unaffected."
                : undefined
            }
            badge={
              queue.data ? (
                <StatusBadge tone={queue.data.storage_ephemeral ? "warning" : "success"}>
                  {queue.data.storage_ephemeral ? "temporary" : "kept"}
                </StatusBadge>
              ) : null
            }
          />
          {health.data?.checks.map((check) => (
            <InfraRow
              key={check.name}
              label={check.name}
              value={check.detail}
              badge={
                <StatusBadge
                  tone={
                    check.status === "pass"
                      ? "success"
                      : check.status === "warn"
                        ? "warning"
                        : "danger"
                  }
                >
                  {check.status.toUpperCase()}
                </StatusBadge>
              }
            />
          ))}
          {config.data ? (
            <InfraRow
              label="corpus"
              value={`${config.data.indexed_chunks} chunks from ${config.data.documents} documents`}
            />
          ) : null}
        </div>
      </Section>
    </div>
  );
}

function SettingRow({ setting }: { setting: SettingDescriptor }) {
  return (
    <div className="grid gap-1 px-3 py-2.5 sm:grid-cols-[16rem_1fr] sm:gap-4">
      <div className="min-w-0">
        <div className="text-sm">{setting.label}</div>
        <div className="text-subtle-foreground mt-0.5 font-mono text-[11px]">
          {setting.key}
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-foreground font-mono text-[13px] break-all">
            {setting.value}
          </span>
          {/*
            The distinction the product exists to keep straight: a query-time
            setting is a slider, an indexing-time one is a rebuild. Both are
            reported by the API so the two can never drift apart here.
          */}
          {setting.requires_reindex ? (
            <StatusBadge tone="warning">requires re-index</StatusBadge>
          ) : (
            <StatusBadge tone="neutral">{setting.scope}-time</StatusBadge>
          )}
          {setting.editable_per_request ? (
            <StatusBadge tone="info">per request</StatusBadge>
          ) : null}
        </div>
        {setting.note ? (
          <p className="text-muted-foreground mt-1.5 text-xs leading-snug">
            {setting.note}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function InfraRow({
  label,
  value,
  note,
  badge,
}: {
  label: string;
  value: string;
  note?: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="grid gap-1 px-3 py-2.5 sm:grid-cols-[16rem_1fr] sm:gap-4">
      <div className="font-mono text-[13px]">{label}</div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground text-[13px]">{value}</span>
          {badge}
        </div>
        {note ? (
          <p className="text-subtle-foreground mt-1.5 text-xs leading-snug">{note}</p>
        ) : null}
      </div>
    </div>
  );
}
