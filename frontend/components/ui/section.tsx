import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A labelled region of a page.
 *
 * Not every group of things needs a card. A section header plus whitespace
 * separates content at a lower visual cost, which keeps the number of framed
 * boxes on a page down to the ones that are genuinely objects.
 */
export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: string;
  /** Controls that act on this section, right-aligned against the title. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <h2 className="text-foreground text-[13px] font-semibold tracking-wide uppercase">
            {title}
          </h2>
          {description ? (
            <p className="text-muted-foreground mt-1 text-sm">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
