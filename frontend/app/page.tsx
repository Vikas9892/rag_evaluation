import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { PendingPanel } from "@/components/pending-panel";
import { ROUTES } from "@/lib/routes";
import { routeMeta } from "@/lib/page-meta";

export default function OverviewPage() {
  const { title, description } = routeMeta("/");
  const destinations = ROUTES.filter((r) => r.href !== "/" && r.href !== "/about");

  return (
    <>
      <PageHeader title={title} description={description} />

      <PendingPanel milestone="Milestone 6">
        Backend health, corpus size and the last benchmark summary, read from{" "}
        <code>GET /health</code> and <code>GET /metrics</code>. Nothing is shown until
        those calls are real: a hardcoded status badge is indistinguishable from a
        measured one, and would be wrong exactly when it matters.
      </PendingPanel>

      <nav aria-label="Sections" className="mt-6 grid gap-3 sm:grid-cols-2">
        {destinations.map((route) => {
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
    </>
  );
}
