import type { Metadata } from "next";

import { ROUTES } from "./routes";

/**
 * Look up a route's label and description from the single route table.
 *
 * Pages read their title from here instead of repeating it, so the sidebar and
 * the page heading cannot drift apart.
 */
export function routeMeta(href: string) {
  const route = ROUTES.find((r) => r.href === href);
  if (!route) {
    throw new Error(
      `No route registered for "${href}". Add it to ROUTES in lib/routes.ts.`,
    );
  }
  return { title: route.label, description: route.description };
}

/** Next.js metadata for a route, derived from the same table. */
export function metadataFor(href: string): Metadata {
  const { title, description } = routeMeta(href);
  return { title: `${title} · RAG Evaluation Platform`, description };
}
