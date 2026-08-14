import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Providers } from "./providers";
import { ApiError } from "@/services/api-error";
import { toast } from "@/components/ui/toast";

function Consumer() {
  const { data } = useQuery({
    queryKey: ["smoke"],
    queryFn: () => Promise.resolve("resolved"),
  });
  return <span>{data ?? "pending"}</span>;
}

/**
 * Surfaces react-query's attempt count so the retry policy is observed rather
 * than assumed. `failureCount` counts every failed attempt, initial included.
 */
function FailingConsumer({ error, queryKey }: { error: Error; queryKey: string }) {
  const { failureCount, isError } = useQuery({
    queryKey: [queryKey],
    queryFn: () => Promise.reject(error),
    retryDelay: 0,
  });
  return (
    <span data-testid="failures">{isError ? `settled:${failureCount}` : "trying"}</span>
  );
}

describe("Providers", () => {
  it("renders children", () => {
    render(
      <Providers>
        <p>child</p>
      </Providers>,
    );
    expect(screen.getByText("child")).toBeInTheDocument();
  });

  it("supplies a QueryClient to descendants", async () => {
    // useQuery throws without a provider, so resolving proves the wiring.
    render(
      <Providers>
        <Consumer />
      </Providers>,
    );
    expect(await screen.findByText("resolved")).toBeInTheDocument();
  });

  it("supplies a toast manager to descendants", async () => {
    // The portal renders client-side only, so SSR markup cannot prove this.
    function Trigger() {
      return <button onClick={() => toast.add({ title: "saved" })}>notify</button>;
    }
    render(
      <Providers>
        <Trigger />
      </Providers>,
    );

    await userEvent.click(screen.getByRole("button", { name: "notify" }));
    expect(await screen.findByText("saved")).toBeInTheDocument();
  });

  describe("default retry policy", () => {
    it("stops immediately on a kind that cannot succeed on a retry", async () => {
      render(
        <Providers>
          <FailingConsumer
            queryKey="unavailable"
            error={new ApiError("unavailable", "no index", { status: 503 })}
          />
        </Providers>,
      );
      expect(await screen.findByText("settled:1")).toBeInTheDocument();
    });

    it("retries a kind that might", async () => {
      render(
        <Providers>
          <FailingConsumer
            queryKey="network"
            error={new ApiError("network", "offline")}
          />
        </Providers>,
      );
      // One initial attempt plus two retries.
      expect(await screen.findByText("settled:3")).toBeInTheDocument();
    });

    it("gives an unrecognised error a single cautious retry", async () => {
      render(
        <Providers>
          <FailingConsumer queryKey="unknown" error={new TypeError("boom")} />
        </Providers>,
      );
      expect(await screen.findByText("settled:2")).toBeInTheDocument();
    });
  });
});
