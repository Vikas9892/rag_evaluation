"use client";

import { Autocomplete } from "@base-ui/react/autocomplete";
import { SearchIcon, XIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/**
 * The question box: free text, suggestions drawn from past questions, and a
 * clear affordance.
 *
 * Built on Base UI's Autocomplete rather than a Combobox because the value here
 * is whatever the user types — the list narrows it, it does not constrain it.
 * A combobox would imply the answer must be one of the options, which is the
 * opposite of asking a question.
 *
 * Suggestions come from history because there is no suggestions endpoint to
 * call; `/query` answers questions, it does not propose them.
 */
export function QuestionInput({
  defaultValue = "",
  suggestions,
  isPending = false,
  onSubmit,
  className,
}: {
  /** Seeds the draft — normally the question already in the URL. */
  defaultValue?: string;
  suggestions: readonly string[];
  isPending?: boolean;
  onSubmit: (question: string) => void;
  className?: string;
}) {
  const [draft, setDraft] = useState(defaultValue);
  const trimmed = draft.trim();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Guarding here as well as by disabling the button: the form can still be
    // submitted with Enter, and an empty question is a guaranteed 400.
    if (!trimmed || isPending) return;
    onSubmit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className={cn("flex items-start gap-2", className)}>
      <Autocomplete.Root
        items={suggestions as string[]}
        value={draft}
        onValueChange={setDraft}
        // The list narrows as you type; the input is never rewritten behind the
        // user's back, which inline completion would do mid-question.
        mode="list"
      >
        <div className="relative flex-1">
          <SearchIcon
            aria-hidden
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          />
          <Autocomplete.Input
            render={
              <Input
                name="question"
                aria-label="Question"
                placeholder="Ask a question about the corpus…"
                autoComplete="off"
                className="pr-8 pl-8"
              />
            }
          />
          {draft ? (
            <Autocomplete.Clear
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Clear question"
                  className="absolute top-1/2 right-1 -translate-y-1/2"
                />
              }
            >
              <XIcon aria-hidden />
            </Autocomplete.Clear>
          ) : null}
        </div>

        {/*
          No popup at all until there is history. An empty suggestion list that
          announces it is empty on every keystroke is worse than no list.
        */}
        {suggestions.length > 0 ? (
          <Autocomplete.Portal>
            <Autocomplete.Positioner sideOffset={4} className="z-50">
              <Autocomplete.Popup className="bg-popover text-popover-foreground max-h-64 w-[var(--anchor-width)] overflow-y-auto rounded-lg border p-1 shadow-lg">
                <Autocomplete.Empty className="text-muted-foreground px-2 py-1.5 text-sm empty:hidden" />
                <Autocomplete.List>
                  {(item: string) => (
                    <Autocomplete.Item
                      key={item}
                      value={item}
                      className="data-highlighted:bg-accent data-highlighted:text-accent-foreground cursor-default truncate rounded-md px-2 py-1.5 text-sm"
                    >
                      {item}
                    </Autocomplete.Item>
                  )}
                </Autocomplete.List>
              </Autocomplete.Popup>
            </Autocomplete.Positioner>
          </Autocomplete.Portal>
        ) : null}
      </Autocomplete.Root>

      <Button type="submit" disabled={!trimmed || isPending}>
        {isPending ? <Spinner aria-label="Asking" /> : null}
        Ask
      </Button>
    </form>
  );
}
