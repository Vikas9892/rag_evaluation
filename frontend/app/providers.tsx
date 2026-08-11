"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/**
 * TanStack Query provider for the whole app.
 *
 * The client is created inside useState rather than at module scope: a module
 * level client would be shared across every request the server handles, leaking
 * one visitor's cached data into another's render.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Every query costs a Groq call. Refetching because a window
            // regained focus would spend real budget for no new information.
            refetchOnWindowFocus: false,
            staleTime: 30_000,
            // Error-class-aware retries land with the typed ApiError in the
            // API-integration milestone; one retry is the conservative default
            // until then, since retrying a 503 or a bad request is pure waste.
            retry: 1,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
