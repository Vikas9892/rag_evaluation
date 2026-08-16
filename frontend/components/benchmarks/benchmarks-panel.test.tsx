import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

function slow(
  retriever: BenchmarkCell["retriever"],
  mrr: number,
  latency: number,
  reranker = false,
): BenchmarkCell {
  const base = cell(retriever, 5, mrr, reranker);
  return {
    ...base,
    metrics: { ...base.metrics, avg_latency_ms: latency, p50_latency_ms: latency },
  };
}

/** Reranking wins on quality by a hair and costs 840 ms. */
const TRADE_OFF: BenchmarkResponse = {
  dataset_size: 53,
  pending: 0,
  cached: true,
  discriminating: true,
  cells: [slow("dense", 0.9, 60), slow("hybrid", 0.905, 900, true)],
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

  describe("the recommendation", () => {
    it("prefers the cheaper configuration when the quality gap is noise", async () => {
      // The highest MRR is not automatically the answer: 0.005 more MRR for
      // 840 ms is not a trade to make in an interactive box.
      getBenchmarks.mockResolvedValue(TRADE_OFF);
      renderPanel();

      const card = (await screen.findByText(/Recommended configuration/)).closest(
        "[data-slot='card']",
      )!;
      expect(within(card as HTMLElement).getByText(/Ship/)).toHaveTextContent(
        "dense · top-5",
      );
    });

    it("states what the more accurate configuration would cost", async () => {
      getBenchmarks.mockResolvedValue(TRADE_OFF);
      renderPanel();

      expect(await screen.findByText(/840 ms more per query/)).toBeInTheDocument();
    });

    it("says there is no trade when the best is also the cheapest", async () => {
      renderPanel();
      expect(await screen.findByText(/no trade to make/i)).toBeInTheDocument();
    });

    it("recommends nothing from a sweep that is still running", async () => {
      // Recommending from a partial matrix means revising it as cells land.
      getBenchmarks.mockResolvedValue({ ...DISCRIMINATING, pending: 4 });
      renderPanel();

      await screen.findByText(/Measuring/);
      expect(screen.queryByText(/Recommended configuration/)).toBeNull();
    });

    it("recommends nothing when no configuration is distinguishable", async () => {
      getBenchmarks.mockResolvedValue(FLAT);
      renderPanel();

      await screen.findByText(/Every configuration scored the same/);
      expect(screen.queryByText(/Recommended configuration/)).toBeNull();
    });
  });

  describe("sorting the matrix", () => {
    const matrixRows = () =>
      within(screen.getByRole("table")).getAllByRole("row").slice(1);

    it("opens on MRR descending rather than in sweep order", async () => {
      renderPanel();
      await screen.findByRole("table");

      expect(within(matrixRows()[0]).getByText("dense")).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /MRR/ })).toHaveAttribute(
        "aria-sort",
        "descending",
      );
    });

    it("sorts by a column when its header is clicked", async () => {
      renderPanel();
      await screen.findByRole("table");

      await userEvent.click(screen.getByRole("button", { name: /Latency/ }));

      expect(screen.getByRole("columnheader", { name: /Latency/ })).toHaveAttribute(
        "aria-sort",
        "ascending",
      );
    });

    it("reverses when the same header is clicked twice", async () => {
      renderPanel();
      await screen.findByRole("table");

      const header = screen.getByRole("button", { name: /Recall/ });
      await userEvent.click(header);
      await userEvent.click(header);

      expect(screen.getByRole("columnheader", { name: /Recall/ })).toHaveAttribute(
        "aria-sort",
        "ascending",
      );
    });

    it("announces which column is not sorted", async () => {
      // aria-sort is how a screen reader learns the table is sorted at all.
      renderPanel();
      await screen.findByRole("table");

      expect(screen.getByRole("columnheader", { name: /Hit rate/ })).toHaveAttribute(
        "aria-sort",
        "none",
      );
    });

    it("leaves the chart's order alone when the table is sorted", async () => {
      // The chart and the table read the same cached array.
      renderPanel();
      await screen.findByRole("table");

      await userEvent.click(screen.getByRole("button", { name: /Latency/ }));

      const chart = screen
        .getByText(/MRR by configuration/)
        .closest("[data-slot='card']")!;
      const first = within(chart as HTMLElement).getAllByRole("listitem")[0];
      expect(first).toHaveTextContent("dense · top-5");
    });
  });
});
