import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ErrorState } from "./error-state";
import { ApiError } from "@/services/api-error";

describe("ErrorState", () => {
  it("renders nothing when there is no error", () => {
    const { container } = render(<ErrorState error={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a cancelled request", () => {
    // A cancellation is the user navigating away or superseding a query. If it
    // rendered, every abandoned search would flash an error at them.
    const { container } = render(
      <ErrorState error={new ApiError("cancelled", "aborted")} onRetry={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("announces the failure to assistive technology", () => {
    render(<ErrorState error={new ApiError("server", "boom")} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  describe("retry affordance", () => {
    it("is offered for a retryable kind", async () => {
      const onRetry = vi.fn();
      render(<ErrorState error={new ApiError("network", "offline")} onRetry={onRetry} />);

      await userEvent.click(screen.getByRole("button", { name: /try again/i }));
      expect(onRetry).toHaveBeenCalledOnce();
    });

    it("is withheld for a 503, which does not fix itself", () => {
      // The whole point of the taxonomy: an unbuilt index will not become built
      // because the user clicked retry three times.
      render(
        <ErrorState
          error={new ApiError("unavailable", "no index", { status: 503 })}
          onRetry={vi.fn()}
        />,
      );
      expect(
        screen.queryByRole("button", { name: /try again/i }),
      ).not.toBeInTheDocument();
    });

    it("is absent when no handler is supplied, even for a retryable kind", () => {
      render(<ErrorState error={new ApiError("timeout", "slow")} />);
      expect(
        screen.queryByRole("button", { name: /try again/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("server detail", () => {
    it("is shown when it is actionable", () => {
      render(
        <ErrorState
          error={
            new ApiError("unavailable", "unavailable", {
              status: 503,
              detail: "FAISS index not built — run scripts/build_index.py",
            })
          }
        />,
      );
      expect(screen.getByText(/build_index\.py/)).toBeInTheDocument();
    });

    it("is suppressed for a 5xx, where it can carry internals", () => {
      render(
        <ErrorState
          error={
            new ApiError("server", "server error", {
              status: 500,
              detail: "Traceback: /srv/app/services/rag_service.py line 88",
            })
          }
        />,
      );
      expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
      expect(screen.getByText(/something broke on the server/i)).toBeInTheDocument();
    });
  });

  it("falls back to generic copy for a non-ApiError", () => {
    render(<ErrorState error={new TypeError("x is not a function")} />);
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    // The raw message is a programmer detail; it is not copy for a user.
    expect(screen.queryByText(/is not a function/)).not.toBeInTheDocument();
  });
});
