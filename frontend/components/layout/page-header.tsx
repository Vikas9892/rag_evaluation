import type { ReactNode } from "react";

/**
 * The top of every page: what this is, and what you can do to it.
 *
 * Deliberately restrained. A 2xl title on a tool that is read all day wastes
 * the space where the first row of data should be, so the title is only one
 * step above a section heading and the description carries the explanation.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  /** Page-level controls, right-aligned and vertically centred on the title. */
  actions?: ReactNode;
}) {
  return (
    <header className="border-border mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b pb-4">
      <div className="min-w-0">
        <h1 className="text-foreground text-lg font-semibold tracking-tight">{title}</h1>
        <p className="text-muted-foreground mt-1 max-w-[70ch] text-sm">{description}</p>
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}
