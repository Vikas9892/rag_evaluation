import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A label beside its control, for a row of settings.
 *
 * Not `Field`: that one is built for a label stacked above its input and sets
 * `*:w-full` on its children, so used in a row both the label and the control
 * stretch to the wrapper's width and overflow it. The result is a toolbar whose
 * items silently overlap once there are enough of them.
 *
 * `shrink-0` because these must keep their intrinsic width and wrap to the next
 * line instead of compressing into each other.
 */
export function InlineField({
  htmlFor,
  label,
  children,
  className,
}: {
  htmlFor: string;
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex shrink-0 items-center gap-2", className)}>
      <label
        htmlFor={htmlFor}
        className="text-muted-foreground text-sm whitespace-nowrap"
      >
        {label}
      </label>
      {children}
    </div>
  );
}
