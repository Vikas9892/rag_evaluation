"use client";

import { UploadIcon } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Mirrors the API's own limits. The server enforces them; this explains them. */
export const ACCEPTED_EXTENSIONS = [".pdf", ".txt", ".md", ".markdown"];
export const MAX_UPLOAD_MB = 25;

/**
 * Drag-and-drop or choose-a-file, with the constraints stated up front.
 *
 * Files are checked here before the request is made, purely so a mistake costs
 * nothing and the reason is immediate. The API re-checks everything — this is
 * a convenience, never the enforcement.
 */
export function UploadDropzone({
  onFiles,
  disabled = false,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function accept(files: FileList | null) {
    if (!files) return;
    const ok: File[] = [];
    const bad: string[] = [];

    for (const file of Array.from(files)) {
      const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(extension)) {
        bad.push(
          `${file.name} — no parser for ${extension || "files without an extension"}`,
        );
      } else if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        bad.push(
          `${file.name} — ${(file.size / 1024 / 1024).toFixed(1)} MB is over the limit`,
        );
      } else if (file.size === 0) {
        bad.push(`${file.name} — the file is empty`);
      } else {
        ok.push(file);
      }
    }

    setRejected(bad);
    if (ok.length) onFiles(ok);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) accept(event.dataTransfer.files);
  }

  return (
    <div className="space-y-2">
      {/*
        A div, not a label wrapping the input: the whole area is a drop target,
        and the button inside it opens the picker. Keyboard users get the
        button, which is why the region itself is not focusable.
      */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        // A row, not a canvas. The old version was a 200px-tall empty
        // rectangle whose height communicated nothing — the drop target only
        // has to be big enough to hit, and the constraints only have to be
        // readable.
        className={cn(
          "flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border border-dashed px-4 py-3.5 transition-colors",
          dragging ? "border-primary/60 bg-primary/5" : "border-border-strong",
          disabled && "pointer-events-none opacity-60",
        )}
      >
        <UploadIcon aria-hidden className="text-muted-foreground size-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Drop documents here</p>
          <p className="text-subtle-foreground mt-0.5 text-xs">
            {ACCEPTED_EXTENSIONS.join(", ")} · up to {MAX_UPLOAD_MB} MB each
          </p>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          onChange={(e) => {
            accept(e.target.files);
            // Cleared so choosing the same file twice fires change again.
            e.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Choose files
        </Button>
      </div>

      {rejected.length > 0 ? (
        <ul className="text-destructive space-y-1 text-xs" role="alert">
          {rejected.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
