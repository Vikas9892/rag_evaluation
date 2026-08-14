import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./error-boundary";

/** React logs every caught error to console.error; that noise is not a failure. */
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
});

function Boom({ shouldThrow }: { shouldThrow: boolean }): React.ReactNode {
  if (shouldThrow) throw new Error("render exploded");
  return <p>content</p>;
}

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <Boom shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("renders a fallback instead of unmounting the whole page", () => {
    render(
      <ErrorBoundary>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("render exploded")).toBeInTheDocument();
  });

  it("reports the error so it can be logged", () => {
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
  });

  it("accepts a custom fallback", () => {
    render(
      <ErrorBoundary fallback={(error) => <p>custom: {error.message}</p>}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );
    expect(screen.getByText("custom: render exploded")).toBeInTheDocument();
  });

  it("recovers when the user resets and the cause is gone", async () => {
    function Harness() {
      const [shouldThrow, setShouldThrow] = useState(true);
      return (
        <>
          <button onClick={() => setShouldThrow(false)}>fix it</button>
          <ErrorBoundary>
            <Boom shouldThrow={shouldThrow} />
          </ErrorBoundary>
        </>
      );
    }
    render(<Harness />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "fix it" }));
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("clears itself when a reset key changes", async () => {
    // Stands in for a route change: without this, a boundary that broke on one
    // page stays broken on the next, because nothing else resets its state.
    function Harness() {
      const [route, setRoute] = useState("/a");
      return (
        <>
          <button onClick={() => setRoute("/b")}>navigate</button>
          <ErrorBoundary resetKeys={[route]}>
            <Boom shouldThrow={route === "/a"} />
          </ErrorBoundary>
        </>
      );
    }
    render(<Harness />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "navigate" }));

    expect(screen.getByText("content")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
