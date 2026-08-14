import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ROUTES } from "@/lib/routes";

import { SidebarNav } from "./sidebar-nav";

const { mockPathname } = vi.hoisted(() => ({ mockPathname: vi.fn() }));

vi.mock("next/navigation", () => ({ usePathname: () => mockPathname() }));

function renderAt(pathname: string) {
  mockPathname.mockReturnValue(pathname);
  return render(<SidebarNav />);
}

describe("SidebarNav", () => {
  it("renders a link for every route", () => {
    renderAt("/");
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(ROUTES.length);
  });

  it("labels the navigation landmark", () => {
    renderAt("/");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("marks the active route with aria-current", () => {
    renderAt("/evaluation");
    expect(screen.getByRole("link", { name: "Evaluation" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks exactly one route active", () => {
    renderAt("/evaluation");
    const current = screen
      .getAllByRole("link")
      .filter((el) => el.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
  });

  it("does not mark inactive routes", () => {
    renderAt("/evaluation");
    expect(screen.getByRole("link", { name: "Query" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("keeps the parent active on a nested path", () => {
    renderAt("/query/some-request-id");
    expect(screen.getByRole("link", { name: "Query" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks no route active on an unknown path", () => {
    renderAt("/totally-unknown");
    const current = screen
      .getAllByRole("link")
      .filter((el) => el.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(0);
  });

  it("points each link at its route href", () => {
    renderAt("/");
    for (const route of ROUTES) {
      expect(screen.getByRole("link", { name: route.label })).toHaveAttribute(
        "href",
        route.href,
      );
    }
  });
});
