import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ApiError } from "@/services/api-error";

import { useHealth } from "./use-health";

const BASE = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeWrapper() {
  const client = new QueryClient({
    // The hook sets its own retry, which is the behaviour under test here.
    defaultOptions: { queries: { refetchInterval: false, retryDelay: 1 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useHealth", () => {
  it("returns the health payload", async () => {
    server.use(
      http.get(`${BASE}/health`, () => HttpResponse.json({ status: "healthy" })),
    );
    const { result } = renderHook(() => useHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toEqual({ status: "healthy" }));
  });

  it("does not retry a 503, because an unbuilt index does not fix itself", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return HttpResponse.json({ detail: "Index not available" }, { status: 503 });
      }),
    );

    const { result } = renderHook(() => useHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(calls).toBe(1);
    expect((result.current.error as ApiError).kind).toBe("unavailable");
  });

  it("does not retry a 400", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return new HttpResponse(null, { status: 400 });
      }),
    );
    const { result } = renderHook(() => useHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(calls).toBe(1);
  });

  it("retries a transient server error, then gives up", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return new HttpResponse(null, { status: 500 });
      }),
    );

    const { result } = renderHook(() => useHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 3000 });

    // Initial attempt plus two retries — bounded, so a dead backend does not
    // produce an endless stream of requests.
    expect(calls).toBe(3);
  });

  it("recovers when a retried request succeeds", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return calls === 1
          ? new HttpResponse(null, { status: 500 })
          : HttpResponse.json({ status: "healthy" });
      }),
    );

    const { result } = renderHook(() => useHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toEqual({ status: "healthy" }));
    expect(calls).toBe(2);
  });
});
