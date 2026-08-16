"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { ROUTES, isActiveRoute } from "@/lib/routes";

/**
 * Primary navigation.
 *
 * Active state is carried three ways on purpose: a surface tint, a left rail,
 * and `aria-current`. Colour alone would be invisible to a screen reader and to
 * anyone who cannot separate two dark greys.
 */
export function SidebarNav({
  orientation = "vertical",
  collapsed = false,
  onNavigate,
}: {
  /** Horizontal is the small-screen strip, where the sidebar is hidden. */
  orientation?: "vertical" | "horizontal";
  /** Icons only. Labels stay in the accessible name via the title attribute. */
  collapsed?: boolean;
  /** Lets a drawer close itself once the reader has chosen a destination. */
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const horizontal = orientation === "horizontal";

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex gap-0.5",
        horizontal ? "overflow-x-auto px-2 py-2" : "flex-col px-2 py-3",
      )}
    >
      {ROUTES.map((route) => {
        const active = isActiveRoute(route.href, pathname);
        const Icon = route.icon;

        return (
          <Link
            key={route.href}
            href={route.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            // The label is the accessible name when expanded; collapsed, the
            // title carries it, so an icon is never unlabelled.
            title={collapsed ? route.label : undefined}
            className={cn(
              "group relative flex items-center rounded-md text-sm transition-colors",
              "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
              horizontal ? "shrink-0 gap-2 px-3 py-1.5" : "gap-2.5 px-2.5 py-2",
              collapsed && !horizontal && "justify-center px-0",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )}
          >
            {/* The rail. Only drawn for the active item, and only in the
                vertical nav where there is an edge for it to sit against. */}
            {active && !horizontal ? (
              <span
                aria-hidden
                className="bg-primary absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full"
              />
            ) : null}
            <Icon
              aria-hidden
              className={cn(
                "size-4 shrink-0",
                active ? "text-foreground" : "text-muted-foreground",
              )}
            />
            {collapsed && !horizontal ? null : (
              <span className="truncate">{route.label}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
