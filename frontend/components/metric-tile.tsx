import { cn } from "@/lib/utils";

/**
 * One measured number, with the caveat that makes it readable.
 *
 * A metric with no context is a number people misread. Precision@5 of 0.21
 * looks like failure until you know it is structurally capped near 0.2 when
 * each question has one relevant chunk and five are retrieved — so the caption
 * is part of the tile, not decoration around it.
 *
 * No colour encodes the value. There is no threshold at which MRR turns green,
 * and inventing one would assert a judgement the data does not carry.
 */
export function MetricTile({
  label,
  value,
  caption,
  className,
}: {
  label: string;
  value: string;
  caption?: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border p-4", className)}>
      <div className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {label}
      </div>
      <div className="mt-1 font-mono text-2xl">{value}</div>
      {caption ? (
        <p className="text-muted-foreground mt-1.5 text-xs leading-snug">{caption}</p>
      ) : null}
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
