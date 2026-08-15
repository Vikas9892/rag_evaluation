"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * Copy text to the clipboard, and say so.
 *
 * The confirmation is the point. Without it the only feedback is a click that
 * appears to do nothing, and the user copies again to be sure.
 */
export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clearing on unmount: the timeout outlives the component otherwise and
  // sets state on something no longer mounted.
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  async function copy() {
    // Not available over plain HTTP or without permission, and it rejects
    // rather than returning false. Saying "copy failed" beats a button that
    // silently pretends.
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setFailed(false);
    } catch {
      setFailed(true);
      setCopied(false);
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 2000);
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={className}
      onClick={() => void copy()}
    >
      {copied ? (
        <CheckIcon aria-hidden className="size-3.5" />
      ) : (
        <CopyIcon aria-hidden className="size-3.5" />
      )}
      {/*
        The label changes rather than only the icon, so the outcome is not
        carried by a glyph alone. aria-live announces it without moving focus.
      */}
      <span aria-live="polite">{failed ? "Copy failed" : copied ? "Copied" : label}</span>
    </Button>
  );
}
