"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { XIcon } from "lucide-react";

import { useSidebarCollapsed } from "@/hooks/use-sidebar";
import { cn } from "@/lib/utils";

import { SidebarNav } from "./sidebar-nav";
import { TopBar } from "./top-bar";

/**
 * The chrome that owns layout state: sidebar collapse and the mobile drawer.
 *
 * `children` arrives already rendered from the server component above, so
 * making this a client island costs nothing beyond the shell itself.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { collapsed, toggle } = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Escape closes the drawer, which is what every overlay on the web does.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="flex min-h-full flex-1">
      <a
        href="#main"
        className="bg-background focus:ring-ring sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:px-3 focus:py-2 focus:ring-2"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          "bg-sidebar border-sidebar-border hidden shrink-0 flex-col border-r transition-[width] duration-200 md:flex",
          collapsed ? "w-14" : "w-56",
        )}
      >
        <SidebarBrand collapsed={collapsed} />
        <SidebarNav collapsed={collapsed} />
        <SidebarFooter collapsed={collapsed} />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/60"
          />
          <div
            role="dialog"
            aria-label="Navigation"
            aria-modal="true"
            className="bg-sidebar border-sidebar-border absolute inset-y-0 left-0 flex w-64 flex-col border-r shadow-xl"
          >
            <div className="border-sidebar-border flex h-12 items-center justify-between border-b px-3">
              <SidebarBrand collapsed={false} />
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close navigation"
                className="text-muted-foreground hover:text-foreground inline-flex size-8 items-center justify-center rounded-md"
              >
                <XIcon aria-hidden className="size-4" />
              </button>
            </div>
            <SidebarNav onNavigate={() => setDrawerOpen(false)} />
            <SidebarFooter collapsed={false} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          collapsed={collapsed}
          onToggleSidebar={toggle}
          onOpenDrawer={() => setDrawerOpen(true)}
        />
        <main id="main" className="min-w-0 flex-1 px-4 py-6 md:px-6 md:py-7">
          <div className="mx-auto w-full max-w-[1180px]">{children}</div>
        </main>
      </div>
    </div>
  );
}

function SidebarBrand({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      className={cn(
        "border-sidebar-border flex h-12 shrink-0 items-center border-b",
        collapsed ? "justify-center px-0" : "px-3",
      )}
    >
      <Link
        href="/"
        className="focus-visible:ring-ring flex items-center gap-2 rounded-md focus-visible:ring-2 focus-visible:outline-none"
        title="RAG Evaluation Platform"
      >
        {/* A mark, not a logo: two stacked bars reading as a ranked result
            list, which is what this product is about. */}
        <span
          aria-hidden
          className="border-primary/40 bg-primary/10 flex size-6 shrink-0 flex-col justify-center gap-[3px] rounded border px-1.5"
        >
          <span className="bg-primary block h-[2px] w-full rounded-full" />
          <span className="bg-primary/60 block h-[2px] w-2/3 rounded-full" />
          <span className="bg-primary/30 block h-[2px] w-1/3 rounded-full" />
        </span>
        {collapsed ? null : (
          <span className="flex min-w-0 flex-col leading-none">
            <span className="text-sidebar-foreground truncate text-[13px] font-semibold">
              RAG Evaluation
            </span>
            <span className="text-subtle-foreground mt-0.5 text-[11px]">Platform</span>
          </span>
        )}
      </Link>
    </div>
  );
}

function SidebarFooter({ collapsed }: { collapsed: boolean }) {
  return (
    <div
      className={cn(
        "border-sidebar-border text-subtle-foreground mt-auto border-t px-3 py-2.5 text-[11px]",
        collapsed && "px-0 text-center",
      )}
    >
      {collapsed ? (
        <span title="Retrieval-only metrics">v1.1</span>
      ) : (
        <span>v1.1 · retrieval-only metrics</span>
      )}
    </div>
  );
}
