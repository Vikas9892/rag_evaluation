import { Construction } from "lucide-react";

/**
 * Placeholder for a surface that is routed but not yet wired to the backend.
 *
 * It states what is missing rather than rendering sample metrics. A mocked
 * Precision@5 or a hardcoded "healthy" badge is indistinguishable from a real
 * one on screen, and this platform's entire claim is that the numbers it shows
 * are measured. Fake data here would undermine that everywhere else.
 */
export function PendingPanel({
  milestone,
  children,
}: {
  milestone: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-border bg-card rounded-lg border border-dashed p-6">
      <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
        <Construction aria-hidden className="size-4" />
        <span>Not yet wired &mdash; {milestone}</span>
      </div>
      <div className="text-muted-foreground mt-3 max-w-2xl text-sm leading-relaxed">
        {children}
      </div>
    </div>
  );
}
