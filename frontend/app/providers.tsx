"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/toast";
import { ApiError } from "@/services/api-error";

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
            // Retry only what could succeed on a second attempt. The taxonomy
            // in api-error.ts already made that call once; repeating the rule
            // per hook would let the two drift apart. An error that isn't an
            // ApiError came from somewhere unexpected, so it gets one cautious
            // attempt rather than the benefit of the doubt.
            retry: (failureCount, error) =>
              error instanceof ApiError
                ? error.retryable && failureCount < 2
                : failureCount < 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {/*
        Toaster wraps the tree rather than sitting beside it: the toast manager
        is context, so anything calling toast() must render inside it.
      */}
      <Toaster>{children}</Toaster>
    </QueryClientProvider>
  );
}
