import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BenchmarksPanel } from "./benchmarks-panel";
import type { BenchmarkCell, BenchmarkResponse } from "@/types/api";

const getBenchmarks = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getBenchmarks }));

function cell(
  retriever: BenchmarkCell["retriever"],
  top_k: number,
  mrr: number,
  reranker = false,
): BenchmarkCell {
  return {
    retriever,
    top_k,
    reranker,
    metrics: {
      precision_at_k: 0.2,
      recall_at_k: 0.9,
      hit_rate: 1,
      mrr,
      avg_latency_ms: 85,
      p50_latency_ms: 85,
      p95_latency_ms: 170,
    },
  };
}

const DISCRIMINATING: BenchmarkResponse = {
  dataset_size: 15,
  pending: 0,
  cached: true,
  discriminating: true,
  cells: [cell("dense", 5, 1.0), cell("hybrid", 5, 0.9133), cell("sparse", 5, 0.8056)],
};

const FLAT: BenchmarkResponse = {
  dataset_size: 15,
  pending: 0,
  cached: true,
  discriminating: false,
  cells: [cell("dense", 5, 1.0), cell("hybrid", 5, 1.0), cell("sparse", 5, 1.0)],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<BenchmarksPanel />, { wrapper: Wrapper });
}

beforeEach(() => {
  getBenchmarks.mockReset();
  getBenchmarks.mockResolvedValue(DISCRIMINATING);
});

describe("BenchmarksPanel", () => {
  it("reports progress instead of a verdict while cells are still pending", async () => {
    // A partial matrix has nothing to conclude from, and announcing a winner
    // the remaining cells might beat would be worse than saying nothing.
    getBenchmarks.mockResolvedValue({ ...DISCRIMINATING, pending: 15, cached: false });
    renderPanel();

    expect(await screen.findByText(/3 of 18 configurations done/)).toBeInTheDocument();
    expect(
      screen.queryByText(/ranks the first relevant chunk highest/),
    ).not.toBeInTheDocument();
  });

  it("lists every configuration", async () => {
    renderPanel();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(4); // header + 3
  });

  it("names the best configuration rather than leaving it to be spotted", async () => {
    renderPanel();
    const verdict = await screen.findByText(/ranks the first relevant chunk highest/);

    expect(verdict).toHaveTextContent("dense · top-5");
    expect(verdict).toHaveTextContent("1.000");
  });

  it("marks the winning row", async () => {
    renderPanel();
    expect(await screen.findByText("best MRR")).toBeInTheDocument();
  });

  it("orders the chart by score", async () => {
    renderPanel();
    await screen.findByText(/ranks the first relevant chunk highest/);
    const bars = screen.getAllByRole("listitem");

    expect(bars[0]).toHaveTextContent("dense · top-5");
    expect(bars[bars.length - 1]).toHaveTextContent("sparse · top-5");
  });

  it("warns that a small dataset is a direction, not a result", async () => {
    renderPanel();
    expect(await screen.findByText(/not a settled result/)).toBeInTheDocument();
  });

  describe("when nothing separates the configurations", () => {
    it("says the corpus is being measured rather than the retrievers", async () => {
      // Presenting a flat matrix as a comparison would be a claim the data
      // does not support.
      getBenchmarks.mockResolvedValue(FLAT);
      renderPanel();

      expect(
        await screen.findByText(/Every configuration scored the same/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/ranks the first relevant chunk highest/),
      ).not.toBeInTheDocument();
    });

    it("still shows the matrix", async () => {
      getBenchmarks.mockResolvedValue(FLAT);
      renderPanel();
      expect(await screen.findByRole("table")).toBeInTheDocument();
    });
  });

  it("explains why Precision@K falls as K rises", async () => {
    // Otherwise the column reads as retrieval getting worse at higher K.
    renderPanel();
    expect(await screen.findByText(/divide the same relevant ones/)).toBeInTheDocument();
  });

  it("surfaces a failure with a retry", async () => {
    getBenchmarks.mockRejectedValue(new Error("boom"));
    renderPanel();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
