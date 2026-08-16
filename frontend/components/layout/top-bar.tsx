"use client";

import { usePathname } from "next/navigation";
import { MenuIcon, PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";

import { ThemeToggle } from "@/components/theme/theme-toggle";
import { ROUTES, isActiveRoute } from "@/lib/routes";

import { HealthIndicator } from "./health-indicator";

/**
 * The top bar: where you are on the left, how the system is on the right.
 *
 * The breadcrumb is derived from the route table rather than typed per page, so
 * a page cannot disagree with the navigation about its own name.
 */
export function TopBar({
  collapsed,
  onToggleSidebar,
  onOpenDrawer,
}: {
  collapsed: boolean;
  onToggleSidebar: () => void;
  onOpenDrawer: () => void;
}) {
  const pathname = usePathname();
  const current = ROUTES.find((route) => isActiveRoute(route.href, pathname));

  const CollapseIcon = collapsed ? PanelLeftOpenIcon : PanelLeftCloseIcon;

  return (
    <header className="border-border bg-background/80 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-30 flex h-12 shrink-0 items-center gap-2 border-b px-3 backdrop-blur md:px-4">
      <button
        type="button"
        onClick={onOpenDrawer}
        aria-label="Open navigation"
        className="text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none md:hidden"
      >
        <MenuIcon aria-hidden className="size-4" />
      </button>

      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring hidden size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none md:inline-flex"
      >
        <CollapseIcon aria-hidden className="size-4" />
      </button>

      {/* Breadcrumb. Two levels is the whole depth of this product, so it is a
          product name and a page, not a growing trail. */}
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
        <span className="text-muted-foreground hidden sm:inline">RAG Evaluation</span>
        <span aria-hidden className="text-border hidden sm:inline">
          /
        </span>
        <span className="text-foreground truncate font-medium">
          {current?.label ?? "Overview"}
        </span>
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <HealthIndicator />
        <span aria-hidden className="bg-border mx-0.5 hidden h-4 w-px sm:block" />
        <ThemeToggle />
      </div>
    </header>
  );
}
