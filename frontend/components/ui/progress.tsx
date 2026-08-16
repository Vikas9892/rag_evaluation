import { cn } from "@/lib/utils";

/**
 * A determinate progress bar.
 *
 * `role="progressbar"` with its aria values, so the number is available to a
 * screen reader rather than existing only as a width. An indeterminate state is
 * deliberately absent: everywhere this is used the backend reports a real
 * fraction, and a bar that animates without measuring anything is decoration.
 */
export function Progress({
  value,
  label,
  tone = "primary",
  className,
}: {
  /** 0–1. Clamped, because a backend rounding to 1.0001 should not overflow. */
  value: number;
  label: string;
  tone?: "primary" | "success" | "warning" | "danger";
  className?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;

  const fill = {
    primary: "bg-primary",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-destructive",
  }[tone];

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("bg-muted h-1.5 w-full overflow-hidden rounded-full", className)}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-300", fill)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/**
 * A horizontal bar used to compare one value against the largest in a set.
 *
 * Separate from Progress because it means something different: this is a
 * magnitude within a comparison, not completion of a task, and it must never
 * be announced as progress.
 */
export function Meter({
  value,
  max,
  className,
}: {
  value: number;
  max: number;
  className?: string;
}) {
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) * 100 : 0;
  return (
    <div
      aria-hidden
      className={cn("bg-muted h-1.5 w-full overflow-hidden rounded-full", className)}
    >
      <div className="bg-chart-1/70 h-full rounded-full" style={{ width: `${pct}%` }} />
    </div>
  );
}
