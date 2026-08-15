"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "rag-eval.theme";

/**
 * Runs before React hydrates, in a blocking script tag.
 *
 * Without it the page paints with the default theme and then corrects itself,
 * which is a white flash on every navigation for anyone using dark mode. This
 * is why the logic is duplicated here as a string: it has to execute before any
 * component code exists.
 */
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(STORAGE_KEY)});
    var theme = stored === "light" || stored === "dark" ? stored : "system";
    var dark = theme === "dark" ||
      (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {
    /* A blocked localStorage must not stop the page rendering. */
  }
})();
`;

interface ThemeContextValue {
  /** What the user chose, including "system". */
  theme: Theme;
  /** What is actually on screen right now. */
  resolved: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

// ---------------------------------------------------------------------------
// The stored choice, as an external store
// ---------------------------------------------------------------------------
//
// The theme lives in localStorage and in the OS, neither of which React owns,
// and the inline script has already applied it to the DOM before React exists.
// Reading it in an effect and calling setState means rendering the wrong theme
// once and correcting it — a cascading render on every page load. useSync-
// ExternalStore subscribes to the real source instead, and its server snapshot
// keeps hydration matching.

const listeners = new Set<() => void>();

/**
 * The choice made this session, which outranks storage.
 *
 * localStorage can throw on write in private mode. Without this the choice
 * would be written nowhere and immediately read back as "system", so clicking
 * Dark would do nothing at all. Held in memory, the theme still applies for
 * the session — it just does not survive a reload.
 */
let chosen: Theme | null = null;

function readStored(): Theme {
  if (chosen !== null) return chosen;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
  } catch {
    /* private mode; fall back to system */
  }
  return "system";
}

// Cached because getSnapshot must return a referentially stable value: React
// calls it during render and re-renders whenever the result differs, so
// recomputing an equal-but-new value would loop.
let themeSnapshot: Theme | null = null;
let resolvedSnapshot: "light" | "dark" | null = null;

function emit() {
  themeSnapshot = null;
  resolvedSnapshot = null;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // "system" tracks the OS, so an OS switch at sunset is a change to this
  // store. An explicit light or dark choice ignores it, which getResolved
  // handles by not consulting the query.
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", emit);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", emit);
  };
}

function getTheme(): Theme {
  themeSnapshot ??= readStored();
  return themeSnapshot;
}

function getResolved(): "light" | "dark" {
  if (resolvedSnapshot === null) {
    const theme = getTheme();
    const dark =
      theme === "dark" ||
      (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    resolvedSnapshot = dark ? "dark" : "light";
  }
  return resolvedSnapshot;
}

/**
 * On the server there is no localStorage and no OS preference.
 *
 * These must be constant: React renders with them and then re-renders with the
 * client value, and a mismatch between the two renders is a hydration error.
 * The inline script means the DOM is already correct either way, so the brief
 * disagreement is invisible.
 */
const serverTheme = (): Theme => "system";
const serverResolved = (): "light" | "dark" => "light";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getTheme, serverTheme);
  const resolved = useSyncExternalStore(subscribe, getResolved, serverResolved);

  // Pushing React's state out to the document element, which is exactly what
  // an effect is for. The inline script did this before hydration; this keeps
  // it true afterwards.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolved === "dark");
    // Tells the browser which scrollbars, form controls and canvas default to.
    document.documentElement.style.colorScheme = resolved;
  }, [resolved]);

  const setTheme = useCallback((next: Theme) => {
    chosen = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* the choice still applies for this session; see `chosen` */
    }
    emit();
  }, []);

  const value = useMemo(
    () => ({ theme, resolved, setTheme }),
    [theme, resolved, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside a ThemeProvider");
  }
  return context;
}
