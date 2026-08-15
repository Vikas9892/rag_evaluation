"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
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

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(theme: Theme): "light" | "dark" {
  const dark = theme === "dark" || (theme === "system" && systemPrefersDark());
  document.documentElement.classList.toggle("dark", dark);
  // Tells the browser which scrollbars, form controls and canvas default to.
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  return dark ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Starts at "system" on both server and client so the first render matches;
  // the inline script has already applied the real theme to the DOM, and the
  // effect below reconciles this state with it.
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");

  useEffect(() => {
    let stored: Theme = "system";
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw === "light" || raw === "dark" || raw === "system") stored = raw;
    } catch {
      /* private mode; fall back to system */
    }
    setThemeState(stored);
    setResolved(apply(stored));
  }, []);

  useEffect(() => {
    // Only "system" tracks the OS. An explicit choice must not be overridden
    // when the machine switches at sunset.
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolved(apply("system"));
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    setResolved(apply(next));
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* the choice still applies for this session */
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside a ThemeProvider");
  }
  return context;
}
