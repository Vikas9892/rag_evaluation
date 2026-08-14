import { render, screen } from "@testing-library/react";
import { SearchIcon } from "lucide-react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders the title and description", () => {
    render(
      <EmptyState title="No chunks retrieved" description="Try a broader question." />,
    );

    expect(screen.getByText("No chunks retrieved")).toBeInTheDocument();
    expect(screen.getByText("Try a broader question.")).toBeInTheDocument();
  });

  it("is not announced as an error", () => {
    // Zero results is a valid answer. Announcing it as an alert would tell the
    // user something broke when nothing did.
    render(<EmptyState title="No results" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders an action when given one", () => {
    render(
      <EmptyState title="No results">
        <button>Clear filters</button>
      </EmptyState>,
    );
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology", () => {
    const { container } = render(<EmptyState icon={SearchIcon} title="No results" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden");
  });

  it("omits the description element when there is no description", () => {
    render(<EmptyState title="No results" />);
    expect(screen.getByText("No results")).toBeInTheDocument();
    expect(document.querySelector('[data-slot="empty-description"]')).toBeNull();
  });
});
