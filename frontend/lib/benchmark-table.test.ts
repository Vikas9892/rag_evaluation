import { describe, expect, it } from "vitest";

import {
  configurationLabel,
  defaultDirection,
  MRR_TOLERANCE,
  nextSort,
  recommend,
  sortCells,
} from "./benchmark-table";
import type { BenchmarkCell } from "@/types/api";

function cell(overrides: {
  retriever?: "dense" | "sparse" | "hybrid";
  top_k?: number;
  reranker?: boolean;
  mrr?: number;
  latency?: number;
}): BenchmarkCell {
  const mrr = overrides.mrr ?? 0.5;
  return {
    retriever: overrides.retriever ?? "dense",
    top_k: overrides.top_k ?? 5,
    reranker: overrides.reranker ?? false,
    metrics: {
      precision_at_k: 0.2,
      recall_at_k: 0.9,
      hit_rate: 0.95,
      mrr,
      avg_latency_ms: overrides.latency ?? 100,
      p50_latency_ms: overrides.latency ?? 100,
      p95_latency_ms: (overrides.latency ?? 100) * 1.5,
    },
  };
}

describe("configurationLabel", () => {
  it("names the retriever, K and whether it reranked", () => {
    expect(
      configurationLabel(cell({ retriever: "hybrid", top_k: 10, reranker: true })),
    ).toBe("hybrid · top-10 · reranked");
  });

  it("says nothing about reranking when it is off", () => {
    expect(configurationLabel(cell({ retriever: "dense", top_k: 5 }))).toBe(
      "dense · top-5",
    );
  });
});

describe("sorting", () => {
  it("opens a quality column at its best value, not its worst", () => {
    // The question a benchmark answers is "which is best", so the first click
    // on MRR must not show the worst configuration.
    expect(defaultDirection("mrr")).toBe("desc");
    expect(defaultDirection("recall_at_k")).toBe("desc");
  });

  it("opens latency and K ascending, where less is the good direction", () => {
    expect(defaultDirection("avg_latency_ms")).toBe("asc");
    expect(defaultDirection("top_k")).toBe("asc");
  });

  it("reverses when the same column is clicked again", () => {
    const first = { key: "mrr" as const, direction: "desc" as const };
    expect(nextSort(first, "mrr")).toEqual({ key: "mrr", direction: "asc" });
  });

  it("starts a different column at its own default rather than inheriting", () => {
    const current = { key: "mrr" as const, direction: "asc" as const };
    expect(nextSort(current, "avg_latency_ms")).toEqual({
      key: "avg_latency_ms",
      direction: "asc",
    });
  });

  it("orders by the chosen metric", () => {
    const cells = [
      cell({ mrr: 0.4 }),
      cell({ mrr: 0.9, top_k: 10 }),
      cell({ mrr: 0.6, top_k: 3 }),
    ];
    const sorted = sortCells(cells, { key: "mrr", direction: "desc" });
    expect(sorted.map((c) => c.metrics.mrr)).toEqual([0.9, 0.6, 0.4]);
  });

  it("orders configuration names alphabetically, not numerically", () => {
    const cells = [cell({ retriever: "sparse" }), cell({ retriever: "dense" })];
    const sorted = sortCells(cells, { key: "configuration", direction: "asc" });
    expect(sorted[0].retriever).toBe("dense");
  });

  it("does not reorder the array it was given", () => {
    // The cells come from the query cache, and the chart above the table reads
    // the same array.
    const cells = [cell({ mrr: 0.4 }), cell({ mrr: 0.9, top_k: 10 })];
    sortCells(cells, { key: "mrr", direction: "desc" });
    expect(cells[0].metrics.mrr).toBe(0.4);
  });

  it("breaks ties deterministically so equal rows do not reshuffle", () => {
    const cells = [
      cell({ retriever: "sparse", mrr: 0.5 }),
      cell({ retriever: "dense", mrr: 0.5 }),
    ];
    const once = sortCells(cells, { key: "mrr", direction: "desc" });
    const twice = sortCells(once, { key: "mrr", direction: "desc" });
    expect(once.map(configurationLabel)).toEqual(twice.map(configurationLabel));
  });
});

describe("recommend", () => {
  it("has nothing to say about an empty matrix", () => {
    expect(recommend([])).toBeNull();
  });

  it("names the highest MRR as best", () => {
    const winner = cell({ retriever: "hybrid", mrr: 0.91, latency: 900 });
    const rec = recommend([cell({ mrr: 0.7 }), winner])!;
    expect(configurationLabel(rec.best)).toBe(configurationLabel(winner));
  });

  it("prefers the cheaper configuration when the quality gap is noise", () => {
    // A reranked run that wins by less than one question's worth of MRR and
    // costs 800 ms is not the configuration to ship.
    const fast = cell({ retriever: "dense", mrr: 0.9, latency: 60 });
    const slow = cell({ retriever: "hybrid", reranker: true, mrr: 0.91, latency: 900 });

    const rec = recommend([fast, slow])!;

    expect(configurationLabel(rec.value)).toBe(configurationLabel(fast));
    expect(rec.agreed).toBe(false);
    expect(rec.extraLatencyMs).toBe(840);
  });

  it("keeps the slower configuration when it is meaningfully better", () => {
    const fast = cell({ retriever: "dense", mrr: 0.6, latency: 60 });
    const slow = cell({ retriever: "hybrid", reranker: true, mrr: 0.9, latency: 900 });

    const rec = recommend([fast, slow])!;

    expect(configurationLabel(rec.value)).toBe(configurationLabel(slow));
    expect(rec.agreed).toBe(true);
  });

  it("treats a gap exactly at the tolerance as noise", () => {
    const fast = cell({ retriever: "dense", mrr: 0.9 - MRR_TOLERANCE, latency: 10 });
    const slow = cell({ retriever: "hybrid", mrr: 0.9, latency: 500 });

    expect(configurationLabel(recommend([fast, slow])!.value)).toBe(
      configurationLabel(fast),
    );
  });

  it("reports no trade-off when the best is also the fastest", () => {
    const best = cell({ retriever: "dense", mrr: 0.9, latency: 40 });
    const rec = recommend([best, cell({ retriever: "sparse", mrr: 0.5, latency: 800 })])!;

    expect(rec.agreed).toBe(true);
    expect(rec.extraLatencyMs).toBe(0);
    expect(rec.extraMrr).toBe(0);
  });

  it("does not reorder the array it was given", () => {
    const cells = [cell({ mrr: 0.4 }), cell({ mrr: 0.9, top_k: 10 })];
    recommend(cells);
    expect(cells[0].metrics.mrr).toBe(0.4);
  });
});
