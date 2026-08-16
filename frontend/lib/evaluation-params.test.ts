import { describe, expect, it } from "vitest";

import {
  buildEvaluationQuery,
  EVAL_RETRIEVER_DEFAULT,
  parseEvaluationParams,
  VIEW_DEFAULT,
} from "./evaluation-params";
import { TOP_K_DEFAULT } from "./query-params";

const parse = (search: string) => parseEvaluationParams(new URLSearchParams(search));

describe("parseEvaluationParams", () => {
  it("defaults every setting when the URL is empty", () => {
    expect(parse("")).toEqual({
      topK: TOP_K_DEFAULT,
      retriever: EVAL_RETRIEVER_DEFAULT,
      view: VIEW_DEFAULT,
    });
  });

  it("reads a run the URL describes", () => {
    expect(parse("?top_k=10&retriever=hybrid&view=worst")).toEqual({
      topK: 10,
      retriever: "hybrid",
      view: "worst",
    });
  });

  it.each(["0", "999", "-3", "abc", "1e1", "", " 5 x"])(
    "repairs an unusable top_k of %s rather than sending it",
    (raw) => {
      // These come from the address bar, which is untrusted input. A value the
      // API refuses would turn a typo into an error banner.
      const { topK } = parse(`?top_k=${encodeURIComponent(raw)}`);
      expect(topK).toBeGreaterThanOrEqual(1);
      expect(topK).toBeLessThanOrEqual(20);
    },
  );

  it("clamps rather than rejects a top_k just out of range", () => {
    expect(parse("?top_k=25").topK).toBe(20);
    expect(parse("?top_k=0").topK).toBe(1);
  });

  it("falls back on a retriever the API does not accept", () => {
    expect(parse("?retriever=magic").retriever).toBe(EVAL_RETRIEVER_DEFAULT);
  });

  it("falls back on an unknown view", () => {
    expect(parse("?view=sideways").view).toBe(VIEW_DEFAULT);
  });
});

describe("buildEvaluationQuery", () => {
  it("omits defaults so the common link stays short", () => {
    expect(
      buildEvaluationQuery({
        topK: TOP_K_DEFAULT,
        retriever: EVAL_RETRIEVER_DEFAULT,
        view: VIEW_DEFAULT,
      }),
    ).toBe("");
  });

  it("round-trips a fully specified run", () => {
    const original = { topK: 12, retriever: "sparse" as const, view: "missed" as const };
    expect(parse(buildEvaluationQuery(original))).toEqual(original);
  });
});
