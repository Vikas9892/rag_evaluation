"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "rag-eval.sidebar-collapsed";

// The preference lives in localStorage, which React does not own. Reading it in
// an effect and calling setState renders the wrong width once and corrects it —
// a cascading render on every page load, and the lint rule against setting
// state from an effect is right to object. useSyncExternalStore subscribes to
// the real source instead, and its server snapshot keeps hydration matching.
// Same shape as the theme store, deliberately.

const listeners = new Set<() => void>();

/** The choice made this session, which outranks storage when it cannot write. */
let chosen: boolean | null = null;
let snapshot: boolean | null = null;

function read(): boolean {
  if (chosen !== null) return chosen;
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    /* private mode: the sidebar simply starts expanded every time */
    return false;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): boolean {
  snapshot ??= read();
  return snapshot;
}

/** The server has no localStorage; expanded is the wider, safer first paint. */
function getServerSnapshot(): boolean {
  return false;
}

export function useSidebarCollapsed(): { collapsed: boolean; toggle: () => void } {
  const collapsed = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = useCallback(() => {
    chosen = !getSnapshot();
    try {
      localStorage.setItem(STORAGE_KEY, chosen ? "1" : "0");
    } catch {
      /* the choice still applies for this session; see `chosen` */
    }
    snapshot = null;
    for (const listener of listeners) listener();
  }, []);

  return { collapsed, toggle };
}
