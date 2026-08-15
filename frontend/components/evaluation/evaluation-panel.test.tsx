import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationPanel } from "./evaluation-panel";
import type { EvaluationResponse } from "@/types/api";

const getEvaluation = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getEvaluation }));

const RESPONSE: EvaluationResponse = {
  top_k: 5,
  retriever: "hybrid",
  dataset_size: 2,
  cached: false,
  metrics: {
    precision_at_k: 0.2133,
    recall_at_k: 0.9667,
    hit_rate: 1,
    mrr: 0.9133,
    avg_latency_ms: 85,
  },
  questions: [
    {
      id: 1,
      question: "What is ACID?",
      hit: true,
      precision: 0.2,
      recall: 1,
      reciprocal_rank: 1,
      latency_ms: 84.2,
      retrieved_ids: ["dbms.md_chunk_0000"],
      expected_ids: ["dbms.md_chunk_0000"],
    },
    {
      id: 2,
      question: "What is a deadlock?",
      hit: false,
      precision: 0,
      recall: 0,
      reciprocal_rank: 0,
      latency_ms: 86.1,
      retrieved_ids: ["os.md_chunk_0002"],
      expected_ids: ["os.md_chunk_0009"],
    },
  ],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<EvaluationPanel />, { wrapper: Wrapper });
}

beforeEach(() => {
  getEvaluation.mockReset();
  getEvaluation.mockResolvedValue(RESPONSE);
});

describe("EvaluationPanel", () => {
  it("shows the four retrieval metrics", async () => {
    renderPanel();
    await screen.findByText("Precision@K");

    // "Recall" is also a column header below, so assert the tile values,
    // which are unique to the tiles.
    for (const value of ["0.213", "0.967", "0.913", "1.000"]) {
      expect(screen.getAllByText(value).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Precision@K")).toBeInTheDocument();
    expect(screen.getByText("Hit rate")).toBeInTheDocument();
  });

  it("explains why Precision@K looks low", async () => {
    // Without the caption 0.213 reads as a failing grade rather than as
    // arithmetic: one relevant chunk out of five retrieved caps it at 0.2.
    renderPanel();
    expect(await screen.findByText(/Capped near 0.20 here/)).toBeInTheDocument();
  });

  it("lists every question, not just the average", async () => {
    // An average hides which questions fail, which is the thing worth fixing.
    renderPanel();
    const table = await screen.findByRole("table");

    expect(within(table).getAllByRole("row")).toHaveLength(3); // header + 2
    expect(screen.getByText("What is a deadlock?")).toBeInTheDocument();
  });

  it("marks a missed question in text, not only by icon", async () => {
    renderPanel();
    await screen.findByRole("table");

    expect(screen.getByText("missed")).toBeInTheDocument();
    expect(screen.getByText("retrieved")).toBeInTheDocument();
  });

  it("says which configuration produced the numbers", async () => {
    renderPanel();
    expect(await screen.findByText(/hybrid retrieval at top-5/)).toBeInTheDocument();
  });

  it("surfaces a failure with a retry", async () => {
    getEvaluation.mockRejectedValue(new Error("boom"));
    renderPanel();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
