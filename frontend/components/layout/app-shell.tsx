import type { ReactNode } from "react";

import { AppFrame } from "./app-frame";

/**
 * Application chrome.
 *
 * A server component that composes the client frame, so `children` are still
 * rendered on the server and only the shell's own layout state ships as JS
 * (ADR 008).
 */
export function AppShell({ children }: { children: ReactNode }) {
  return <AppFrame>{children}</AppFrame>;
}
