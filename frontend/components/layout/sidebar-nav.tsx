"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { ROUTES, isActiveRoute } from "@/lib/routes";

/**
 * Primary navigation.
 *
 * This is the only client component in the layout: active-link highlighting
 * needs usePathname. The surrounding shell stays a server component, so the
 * client boundary is drawn as tightly as the feature allows (ADR 008).
 */
export function SidebarNav({
  orientation = "vertical",
}: {
  /** Horizontal is the small-screen layout, where the sidebar is hidden. */
  orientation?: "vertical" | "horizontal";
}) {
  const pathname = usePathname();
  const horizontal = orientation === "horizontal";

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "flex gap-1",
        horizontal ? "overflow-x-auto px-2 py-2" : "flex-col p-3",
      )}
    >
      {ROUTES.map((route) => {
        const active = isActiveRoute(route.href, pathname);
        const Icon = route.icon;

        return (
          <Link
            key={route.href}
            href={route.href}
            // aria-current is what a screen reader announces as "current page";
            // colour alone would leave that state invisible to it.
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
              horizontal ? "shrink-0" : "gap-3",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
            )}
          >
            <Icon aria-hidden className="size-4 shrink-0" />
            <span className="truncate">{route.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
