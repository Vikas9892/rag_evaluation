import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MeasuredQuality } from "./measured-quality";

const getEvaluation = vi.hoisted(() => vi.fn());
const getConfig = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getEvaluation, getConfig }));

const EVALUATION = {
  top_k: 5,
  retriever: "dense" as const,
  reranker: false,
  dataset_size: 53,
  cached: true,
  metrics: {
    precision_at_k: 0.2,
    recall_at_k: 0.9623,
    hit_rate: 0.9623,
    mrr: 0.878,
    avg_latency_ms: 80.2,
    p50_latency_ms: 64.1,
    p95_latency_ms: 120.3,
  },
  questions: [],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<MeasuredQuality />, { wrapper: Wrapper });
}

beforeEach(() => {
  getEvaluation.mockReset().mockResolvedValue(EVALUATION);
  getConfig.mockReset().mockResolvedValue({ indexed_chunks: 212 });
});

describe("MeasuredQuality", () => {
  it("reports what the API measured, not a number typed into the page", async () => {
    // The hardcoded list this replaced still claimed Recall 1.00 and MRR 1.00
    // long after the dataset had more than tripled.
    renderPanel();

    expect(await screen.findByText("0.962")).toBeInTheDocument();
    expect(screen.getByText("0.878")).toBeInTheDocument();
  });

  it("reports the median latency rather than the mean", async () => {
    renderPanel();
    expect(await screen.findByText("64 ms")).toBeInTheDocument();
  });

  it("says how many questions the numbers came from", async () => {
    renderPanel();
    expect(await screen.findByText(/53 labelled questions/)).toBeInTheDocument();
  });

  it("explains the Precision cap from the K it actually ran at", async () => {
    renderPanel();
    expect(await screen.findByText(/capped near 0.20/i)).toBeInTheDocument();
  });

  it("measures the shipped default, not the best configuration", async () => {
    // Quoting the winning benchmark cell here would advertise a configuration
    // the product does not use.
    renderPanel();

    await screen.findByText("0.962");
    expect(getEvaluation.mock.calls[0].slice(0, 2)).toEqual([5, "dense"]);
  });

  it("shows nothing rather than stale numbers when the API is unreachable", async () => {
    getEvaluation.mockRejectedValue(new Error("offline"));
    renderPanel();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("0.962")).toBeNull();
  });

  it("still reports the metrics when the corpus size is unavailable", async () => {
    // The chunk count is context, not the measurement.
    getConfig.mockRejectedValue(new Error("offline"));
    renderPanel();

    expect(await screen.findByText("0.962")).toBeInTheDocument();
  });
});
