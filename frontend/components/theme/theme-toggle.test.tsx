import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider, useTheme } from "./theme-provider";
import { ThemeToggle } from "./theme-toggle";

function setSystemDark(dark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: dark && query.includes("dark"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  }));
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
  setSystemDark(false);
});
afterEach(() => {
  vi.restoreAllMocks();
});

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

describe("ThemeToggle", () => {
  it("offers light, dark and system", () => {
    renderToggle();
    for (const name of ["Light", "Dark", "System"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("applies dark mode to the document", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(document.documentElement).toHaveClass("dark");
  });

  it("removes dark mode again", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    await userEvent.click(screen.getByRole("button", { name: "Light" }));

    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("sets color-scheme so scrollbars and form controls follow", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("persists the choice", async () => {
    renderToggle();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(window.localStorage.getItem("rag-eval.theme")).toBe("dark");
  });

  it("restores a stored choice on mount", async () => {
    window.localStorage.setItem("rag-eval.theme", "dark");
    renderToggle();

    expect(
      await screen.findByRole("button", { name: "Dark", pressed: true }),
    ).toBeInTheDocument();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("follows the system when system is chosen", async () => {
    setSystemDark(true);
    renderToggle();

    await userEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.documentElement).toHaveClass("dark");
  });

  it("keeps system as a distinct choice rather than an absence of one", async () => {
    // A two-way switch silently opts the user out of following their machine,
    // with no way back.
    setSystemDark(true);
    renderToggle();

    await userEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement).not.toHaveClass("dark");

    await userEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.documentElement).toHaveClass("dark");
  });

  it("announces the selection rather than relying on the highlight", async () => {
    // A screen reader cannot see which segment is shaded.
    renderToggle();
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("survives localStorage being unavailable", async () => {
    // Safari in private mode throws on access; a theme preference is not worth
    // taking the page down for.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    renderToggle();

    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveClass("dark");
  });
});

describe("useTheme", () => {
  it("refuses to be used outside the provider", () => {
    // Silently returning a default would make a mis-nested toggle look like it
    // works while changing nothing.
    function Orphan() {
      useTheme();
      return null;
    }
    vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Orphan />)).toThrow(/ThemeProvider/);
  });
});
