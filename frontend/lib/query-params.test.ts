import { describe, expect, it } from "vitest";

import {
  buildQueryString,
  parseQueryParams,
  RETRIEVERS,
  CORPUS_DEFAULT,
  RETRIEVER_DEFAULT,
  TOP_K_DEFAULT,
  TOP_K_MAX,
  TOP_K_MIN,
} from "./query-params";

const parse = (search: string) => parseQueryParams(new URLSearchParams(search));

describe("parseQueryParams", () => {
  it("reads a question and top_k", () => {
    expect(parse("?q=what+is+ACID&top_k=8")).toEqual({
      q: "what is ACID",
      topK: 8,
      retriever: RETRIEVER_DEFAULT,
      reranker: false,
      corpus: CORPUS_DEFAULT,
    });
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
    expect(
      buildQueryString({
        q: "hello",
        topK: TOP_K_DEFAULT,
        retriever: RETRIEVER_DEFAULT,
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("?q=hello");
  });

  it("includes a non-default top_k", () => {
    expect(
      buildQueryString({
        q: "hello",
        topK: 10,
        retriever: RETRIEVER_DEFAULT,
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("?q=hello&top_k=10");
  });

  it("returns an empty string when there is nothing to carry", () => {
    expect(
      buildQueryString({
        q: "",
        topK: TOP_K_DEFAULT,
        retriever: RETRIEVER_DEFAULT,
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("");
  });

  it("encodes characters that would otherwise break the URL", () => {
    const encoded = buildQueryString({
      q: "a&b=c?d #e",
      topK: TOP_K_DEFAULT,
      retriever: RETRIEVER_DEFAULT,
      reranker: false,
      corpus: CORPUS_DEFAULT,
    });
    expect(encoded).not.toMatch(/[ #]/);
    expect(parse(encoded).q).toBe("a&b=c?d #e");
  });

  it("round-trips through parse", () => {
    const original = {
      q: "What is a deadlock?",
      topK: 12,
      retriever: "sparse" as const,
      reranker: false,
      corpus: CORPUS_DEFAULT,
    };
    expect(parse(buildQueryString(original))).toEqual(original);
  });
});

describe("corpus", () => {
  it("defaults to the benchmark corpus when the URL names none", () => {
    expect(parse("?q=hello").corpus).toBe(CORPUS_DEFAULT);
  });

  it("reads a corpus the API would accept", () => {
    expect(parse("?q=hello&corpus=k8s-notes").corpus).toBe("k8s-notes");
  });

  it.each(["../../etc", "Workspace", "-leading", "has space", "a".repeat(65)])(
    "falls back rather than passing on %s",
    (corpus) => {
      // Sanitising would be worse than ignoring: a repaired id names some other
      // corpus, and the answer would come from documents nobody asked about.
      expect(parse(`?q=hello&corpus=${encodeURIComponent(corpus)}`).corpus).toBe(
        CORPUS_DEFAULT,
      );
    },
  );

  it("omits the corpus at its default so the common link stays short", () => {
    expect(
      buildQueryString({
        q: "hello",
        topK: TOP_K_DEFAULT,
        retriever: RETRIEVER_DEFAULT,
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("?q=hello");
  });

  it("round-trips a non-default corpus", () => {
    const original = {
      q: "hello",
      topK: TOP_K_DEFAULT,
      retriever: RETRIEVER_DEFAULT,
      reranker: false,
      corpus: "workspace",
    };
    expect(parse(buildQueryString(original))).toEqual(original);
  });
});

describe("retriever", () => {
  it.each(RETRIEVERS)("accepts %s", (mode) => {
    expect(parse(`?retriever=${mode}`).retriever).toBe(mode);
  });

  it("defaults when absent", () => {
    expect(parse("?q=hello").retriever).toBe(RETRIEVER_DEFAULT);
  });

  it.each([
    ["an unknown strategy", "?retriever=magic"],
    ["an empty value", "?retriever="],
    ["a near miss", "?retriever=Hybrid"],
  ])("falls back for %s rather than sending it to the API", (_label, search) => {
    // The API answers an unknown strategy with 422; a typo in the address bar
    // should not surface as an error banner.
    expect(parse(search).retriever).toBe(RETRIEVER_DEFAULT);
  });

  it("is omitted from the URL at its default", () => {
    expect(
      buildQueryString({
        q: "hello",
        topK: TOP_K_DEFAULT,
        retriever: RETRIEVER_DEFAULT,
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("?q=hello");
  });

  it("is carried in the URL when chosen", () => {
    // Dense is the default now, so it is the one that gets omitted.
    expect(
      buildQueryString({
        q: "hello",
        topK: TOP_K_DEFAULT,
        retriever: "hybrid",
        reranker: false,
        corpus: CORPUS_DEFAULT,
      }),
    ).toBe("?q=hello&retriever=hybrid");
  });

  it("survives a round trip alongside top_k", () => {
    const original = {
      q: "hello",
      topK: 12,
      retriever: "sparse" as const,
      reranker: false,
      corpus: CORPUS_DEFAULT,
    };
    expect(parse(buildQueryString(original))).toEqual(original);
  });
});
