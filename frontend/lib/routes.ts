import {
  BarChart3,
  FlaskConical,
  FolderOpen,
  Info,
  LayoutDashboard,
  Search,
  Settings,
  type LucideIcon,
} from "lucide-react";

/**
 * The application's routes, in navigation order.
 *
 * One table drives the sidebar, the page metadata and the navigation tests, so
 * a route cannot exist in the nav without existing as a page — or vice versa.
 */
export interface AppRoute {
  href: string;
  label: string;
  /** Shown under the page title; also the route's meta description. */
  description: string;
  icon: LucideIcon;
}

export const ROUTES: readonly AppRoute[] = [
  {
    href: "/",
    label: "Overview",
    description: "What this platform does, what is indexed, and whether it is working.",
    icon: LayoutDashboard,
  },
  {
    href: "/workspace",
    label: "Workspace",
    description: "Upload documents, watch them index, then query your own corpus.",
    icon: FolderOpen,
  },
  {
    href: "/query",
    label: "Query",
    description: "Ask a question and inspect the retrieval trace behind the answer.",
    icon: Search,
  },
  {
    href: "/evaluation",
    label: "Evaluation",
    description: "Precision@K, Recall and MRR measured over the labelled dataset.",
    icon: FlaskConical,
  },
  {
    href: "/benchmarks",
    label: "Benchmarks",
    description: "Compare chunk size, top-K and retriever configurations.",
    icon: BarChart3,
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Retrieval knobs applied to queries in this session.",
    icon: Settings,
  },
  {
    href: "/about",
    label: "About",
    description: "How the pipeline works and why it is built this way.",
    icon: Info,
  },
] as const;

/**
 * True when `href` is the active route for `pathname`.
 *
 * "/" matches only itself; every other route also matches its descendants, so
 * a future /query/abc still highlights Query.
 */
export function isActiveRoute(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
