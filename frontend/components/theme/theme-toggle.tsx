"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";

import { useTheme, type Theme } from "@/components/theme/theme-provider";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Theme; label: string; Icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "System", Icon: MonitorIcon },
];

/**
 * A three-way segmented control, not a two-way switch.
 *
 * "System" is a distinct choice, not the absence of one: a toggle that only
 * flips light and dark silently opts the user out of following their machine,
 * and there is then no way back to it.
 *
 * Selection is carried by `aria-pressed` and a visually-hidden label rather
 * than by the highlight alone, which a screen reader cannot see.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className={cn(
        "border-border bg-muted/40 flex gap-0.5 rounded-md border p-0.5",
        className,
      )}
      role="group"
      aria-label="Colour theme"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => setTheme(value)}
            aria-pressed={active}
            title={label}
            className={cn(
              "focus-visible:ring-ring flex size-6 flex-1 items-center justify-center rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none",
              active
                ? "bg-elevated text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon aria-hidden className="size-3.5" />
            <span className="sr-only">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
