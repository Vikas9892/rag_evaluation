import Link from "next/link";
import type { ReactNode } from "react";

import { HealthIndicator } from "./health-indicator";
import { SidebarNav } from "./sidebar-nav";

/**
 * Application chrome: sidebar, top bar and the main content region.
 *
 * A server component — it renders no interactive state of its own and only
 * composes the client nav island.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1">
      {/* Keyboard users land here first and can jump past the nav. */}
      <a
        href="#main"
        className="bg-background focus:ring-ring sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:px-3 focus:py-2 focus:ring-2"
      >
        Skip to content
      </a>

      <aside className="bg-sidebar border-sidebar-border hidden w-60 shrink-0 flex-col border-r md:flex">
        <div className="border-sidebar-border flex h-14 items-center border-b px-4">
          <Link href="/" className="flex flex-col leading-tight">
            <span className="text-sidebar-foreground text-sm font-semibold">
              RAG Evaluation
            </span>
            <span className="text-muted-foreground text-xs">Platform</span>
          </Link>
        </div>
        <SidebarNav />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-border bg-background flex h-14 shrink-0 items-center gap-4 border-b px-4 md:px-6">
          <Link href="/" className="text-sm font-semibold md:hidden">
            RAG Evaluation
          </Link>
          <div className="ml-auto text-xs">
            <HealthIndicator />
          </div>
        </header>

        {/* Below md the sidebar is hidden, so the nav becomes a scrolling strip. */}
        <div className="border-border bg-sidebar border-b md:hidden">
          <SidebarNav orientation="horizontal" />
        </div>

        <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
