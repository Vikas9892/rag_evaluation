import { describe, expect, it } from "vitest";

import {
  buildQueryString,
  parseQueryParams,
  TOP_K_DEFAULT,
  TOP_K_MAX,
  TOP_K_MIN,
} from "./query-params";

const parse = (search: string) => parseQueryParams(new URLSearchParams(search));

describe("parseQueryParams", () => {
  it("reads a question and top_k", () => {
    expect(parse("?q=what+is+ACID&top_k=8")).toEqual({ q: "what is ACID", topK: 8 });
  });

  it("defaults an absent top_k", () => {
    expect(parse("?q=hello").topK).toBe(TOP_K_DEFAULT);
  });

  it("treats a missing question as empty rather than undefined", () => {
    expect(parse("").q).toBe("");
  });

  it("trims surrounding whitespace from the question", () => {
    expect(parse("?q=%20%20spaced%20%20").q).toBe("spaced");
  });

  describe("top_k from an untrusted URL", () => {
    it.each([
      ["above the maximum", `?top_k=${TOP_K_MAX + 500}`, TOP_K_MAX],
      ["below the minimum", "?top_k=0", TOP_K_MIN],
      ["not a number", "?top_k=banana", TOP_K_DEFAULT],
      ["empty", "?top_k=", TOP_K_DEFAULT],
      ["negative", "?top_k=-4", TOP_K_DEFAULT],
      ["fractional", "?top_k=3.7", TOP_K_DEFAULT],
      // Number() would accept all three of these; the API would not.
      ["hexadecimal", "?top_k=0x10", TOP_K_DEFAULT],
      ["exponential", "?top_k=1e1", TOP_K_DEFAULT],
      ["infinity", "?top_k=Infinity", TOP_K_DEFAULT],
    ])("clamps or rejects %s", (_label, search, expected) => {
      expect(parse(search).topK).toBe(expected);
    });

    it("never returns a value the API would reject", () => {
      for (const raw of ["0", "1", "20", "21", "9999", "abc", "-1", ""]) {
        const { topK } = parse(`?top_k=${raw}`);
        expect(topK).toBeGreaterThanOrEqual(TOP_K_MIN);
        expect(topK).toBeLessThanOrEqual(TOP_K_MAX);
        expect(Number.isInteger(topK)).toBe(true);
      }
    });
  });
});

describe("buildQueryString", () => {
  it("omits top_k at its default so links to the same question compare equal", () => {
    expect(buildQueryString({ q: "hello", topK: TOP_K_DEFAULT })).toBe("?q=hello");
  });

  it("includes a non-default top_k", () => {
    expect(buildQueryString({ q: "hello", topK: 10 })).toBe("?q=hello&top_k=10");
  });

  it("returns an empty string when there is nothing to carry", () => {
    expect(buildQueryString({ q: "", topK: TOP_K_DEFAULT })).toBe("");
  });

  it("encodes characters that would otherwise break the URL", () => {
    const encoded = buildQueryString({ q: "a&b=c?d #e", topK: TOP_K_DEFAULT });
    expect(encoded).not.toMatch(/[ #]/);
    expect(parse(encoded).q).toBe("a&b=c?d #e");
  });

  it("round-trips through parse", () => {
    const original = { q: "What is a deadlock?", topK: 12 };
    expect(parse(buildQueryString(original))).toEqual(original);
  });
});
