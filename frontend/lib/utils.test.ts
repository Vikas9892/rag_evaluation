import { describe, expect, it } from "vitest";

import { cn } from "./utils";

describe("cn", () => {
  it("joins class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy values", () => {
    expect(cn("a", false && "b", undefined, null, "c")).toBe("a c");
  });

  it("lets a later Tailwind class win over an earlier conflicting one", () => {
    // The whole reason for tailwind-merge over plain clsx: a variant's default
    // padding must be overridable by a caller's prop without !important.
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("keeps non-conflicting Tailwind classes", () => {
    expect(cn("px-2", "py-4")).toBe("px-2 py-4");
  });
});
