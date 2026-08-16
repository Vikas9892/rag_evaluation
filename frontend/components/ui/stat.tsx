import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * One measured number, with the caveat that makes it readable.
 *
 * A metric with no context is a number people misread. Precision@5 of 0.200
 * looks like failure until you know it is structurally capped near 1/K when
 * each question has one relevant chunk and five are retrieved — so the caption
 * is part of the tile, not decoration around it.
 *
 * No colour encodes the value. There is no threshold at which MRR turns green,
 * and inventing one would assert a judgement the data does not carry. Tone is
 * available for the cases where a value genuinely is a failure count.
 */
export function Stat({
  label,
  value,
  caption,
  unit,
  tone,
  className,
}: {
  label: string;
  value: ReactNode;
  caption?: string;
  /** Rendered smaller and muted after the value: "ms", "chunks". */
  unit?: string;
  tone?: "danger" | "warning";
  className?: string;
}) {
  return (
    <div className={cn("border-border bg-card rounded-lg border p-3.5", className)}>
      <div className="text-muted-foreground text-[11px] font-medium tracking-wider uppercase">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span
          className={cn(
            "font-mono text-[22px] leading-none tracking-tight tabular-nums",
            tone === "danger" && "text-destructive",
            tone === "warning" && "text-warning",
          )}
        >
          {value}
        </span>
        {unit ? (
          <span className="text-muted-foreground font-mono text-xs">{unit}</span>
        ) : null}
      </div>
      {caption ? (
        <p className="text-subtle-foreground mt-2 text-[11px] leading-snug">{caption}</p>
      ) : null}
    </div>
  );
}

/** A label/value pair for dense definition lists — settings, configuration. */
export function KeyValue({
  label,
  value,
  hint,
  mono = true,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  mono?: boolean;
}) {
  return (
    <div className="border-border flex items-start justify-between gap-4 border-b py-2 last:border-b-0">
      <div className="min-w-0">
        <div className="text-foreground text-sm">{label}</div>
        {hint ? (
          <p className="text-subtle-foreground mt-0.5 text-xs leading-snug">{hint}</p>
        ) : null}
      </div>
      <div
        className={cn(
          "text-muted-foreground shrink-0 text-right text-sm",
          mono && "font-mono tabular-nums",
        )}
      >
        {value}
      </div>
    </div>
  );
}

/** Formats a 0–1 metric without pretending to precision it does not have. */
export function ratio(value: number): string {
  return value.toFixed(3);
}

export function ms(value: number): string {
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 100) return `${value.toFixed(1)} ms`;
  return `${Math.round(value)} ms`;
}
