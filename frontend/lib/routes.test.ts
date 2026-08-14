import { existsSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { ROUTES, isActiveRoute } from "./routes";
import { metadataFor, routeMeta } from "./page-meta";

describe("isActiveRoute", () => {
  it("matches the exact route", () => {
    expect(isActiveRoute("/query", "/query")).toBe(true);
  });

  it("matches descendants so nested pages keep the parent highlighted", () => {
    expect(isActiveRoute("/query", "/query/abc")).toBe(true);
  });

  it("does not match an unrelated route", () => {
    expect(isActiveRoute("/query", "/evaluation")).toBe(false);
  });

  it("does not treat a shared prefix as a descendant", () => {
    // "/benchmarks" must not light up for "/benchmarks-archive".
    expect(isActiveRoute("/benchmarks", "/benchmarks-archive")).toBe(false);
  });

  it("root matches only itself", () => {
    expect(isActiveRoute("/", "/")).toBe(true);
    expect(isActiveRoute("/", "/query")).toBe(false);
  });
});

describe("ROUTES", () => {
  it("has unique hrefs", () => {
    const hrefs = ROUTES.map((r) => r.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("has unique labels", () => {
    const labels = ROUTES.map((r) => r.label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("every href is absolute", () => {
    for (const route of ROUTES) {
      expect(route.href.startsWith("/")).toBe(true);
    }
  });

  it("every route describes itself", () => {
    for (const route of ROUTES) {
      expect(route.description.length).toBeGreaterThan(10);
    }
  });

  /**
   * The nav and the filesystem must agree. Without this, a route can be added
   * to the sidebar and ship as a 404, which no unit test of the nav would catch.
   */
  it("every route has a page on disk", () => {
    for (const route of ROUTES) {
      const segment = route.href === "/" ? "" : route.href;
      const file = path.join(import.meta.dirname, "..", "app", segment, "page.tsx");
      expect(existsSync(file), `missing app${segment}/page.tsx`).toBe(true);
    }
  });
});

describe("routeMeta", () => {
  it("returns the label and description for a known route", () => {
    expect(routeMeta("/query").title).toBe("Query");
  });

  it("throws for an unregistered route rather than rendering a blank title", () => {
    expect(() => routeMeta("/nope")).toThrow(/No route registered/);
  });

  it("suffixes the product name in page metadata", () => {
    expect(metadataFor("/query").title).toBe("Query · RAG Evaluation Platform");
  });
});
