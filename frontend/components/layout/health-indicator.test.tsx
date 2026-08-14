import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/api-error";

import { HealthIndicator } from "./health-indicator";

/**
 * The component is tested against a mocked hook, not a mocked network
 * (docs/frontend_architecture.md). Driving it through MSW would also drag in
 * the hook's retry and backoff policy, which belongs to use-health's own test
 * and would make these assertions slow and timing-dependent.
 */
const { mockUseHealth } = vi.hoisted(() => ({ mockUseHealth: vi.fn() }));
vi.mock("@/hooks/use-health", () => ({ useHealth: () => mockUseHealth() }));

function renderWith(state: { data?: unknown; error?: unknown; isPending?: boolean }) {
  mockUseHealth.mockReturnValue({
    data: state.data,
    error: state.error ?? null,
    isPending: state.isPending ?? false,
  });
  return render(<HealthIndicator />);
}

describe("HealthIndicator", () => {
  it("never claims healthy while the first request is in flight", () => {
    renderWith({ isPending: true });
    expect(screen.getByText("Checking…")).toBeInTheDocument();
  });

  it("reports a healthy backend", () => {
    renderWith({ data: { status: "healthy" } });
    expect(screen.getByText("API healthy")).toBeInTheDocument();
  });

  it("reports an unreachable API for a network error", () => {
    renderWith({ error: new ApiError("network", "Could not reach the API") });
    expect(screen.getByText("API unreachable")).toBeInTheDocument();
  });

  it("reports an unreachable API for a timeout", () => {
    renderWith({ error: new ApiError("timeout", "timed out") });
    expect(screen.getByText("API unreachable")).toBeInTheDocument();
  });

  it("reports degraded when the API answers with an error", () => {
    // A reachable API whose pipeline is broken is a different problem from an
    // API that cannot be reached, and the user fixes them differently.
    renderWith({
      error: new ApiError("unavailable", "unavailable", {
        status: 503,
        detail: "Index not available",
      }),
    });
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("shows the server's own explanation as the tooltip", () => {
    renderWith({
      error: new ApiError("unavailable", "unavailable", {
        status: 503,
        detail: "Index not available",
      }),
    });
    expect(screen.getByTitle("Index not available")).toBeInTheDocument();
  });

  it("handles a non-ApiError rejection without crashing", () => {
    renderWith({ error: new Error("boom") });
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("echoes an unexpected status rather than calling it healthy", () => {
    renderWith({ data: { status: "starting" } });
    expect(screen.getByText("starting")).toBeInTheDocument();
  });

  it("exposes the status to assistive technology", () => {
    renderWith({ data: { status: "healthy" } });
    expect(screen.getByRole("status")).toHaveTextContent("API healthy");
  });

  it("marks the colour dot decorative", () => {
    // Colour is duplicated by the adjacent text, so the dot must not be
    // announced separately.
    renderWith({ data: { status: "healthy" } });
    expect(screen.getByTestId("health-dot")).toHaveAttribute("aria-hidden");
  });
});
