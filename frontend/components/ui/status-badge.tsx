import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * What a thing's state is, in a word and a colour — in that order.
 *
 * The word is the status; the tint reinforces it. Colour alone fails in forced
 * colours, in greyscale, and for anyone who cannot separate the two darkest
 * greens, so every tone here is paired with text the reader can act on.
 */
export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

const TONES: Record<StatusTone, string> = {
  neutral: "border-border text-muted-foreground bg-muted/40",
  success: "border-success/30 text-success bg-success-subtle",
  warning: "border-warning/30 text-warning bg-warning-subtle",
  danger: "border-destructive/30 text-destructive bg-destructive-subtle",
  info: "border-info/30 text-info bg-info-subtle",
};

export function StatusBadge({
  tone = "neutral",
  icon: Icon,
  children,
  className,
}: {
  tone?: StatusTone;
  icon?: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 font-mono text-[11px] leading-4 tracking-tight whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {Icon ? <Icon aria-hidden className="size-3" /> : null}
      {children}
    </span>
  );
}

/** A bare dot plus label, for rows where a bordered chip would be too loud. */
export function StatusDot({
  tone = "neutral",
  children,
  className,
}: {
  tone?: StatusTone;
  children: React.ReactNode;
  className?: string;
}) {
  const dot: Record<StatusTone, string> = {
    neutral: "bg-muted-foreground",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-destructive",
    info: "bg-info",
  };

  return (
    <span className={cn("inline-flex items-center gap-2 text-sm", className)}>
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", dot[tone])} />
      {children}
    </span>
  );
}
