import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationPanel } from "./evaluation-panel";
import type { EvaluationResponse } from "@/types/api";

const getEvaluation = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getEvaluation }));

const replace = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => "/evaluation",
  useSearchParams: () => searchParams,
}));

const RESPONSE: EvaluationResponse = {
  top_k: 5,
  retriever: "hybrid",
  reranker: false,
  dataset_size: 2,
  cached: false,
  metrics: {
    precision_at_k: 0.2133,
    recall_at_k: 0.9667,
    hit_rate: 1,
    mrr: 0.9133,
    avg_latency_ms: 85,
    p50_latency_ms: 85,
    p95_latency_ms: 170,
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
  replace.mockReset();
  searchParams = new URLSearchParams();
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
    // Scoped to the table: a missed question also appears in the Failures
    // card above, which is the point of that card.
    expect(within(table).getByText("What is a deadlock?")).toBeInTheDocument();
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

  describe("run controls", () => {
    it("runs at the top-K in the URL, so a result can be linked to", async () => {
      searchParams = new URLSearchParams("?top_k=10&retriever=sparse");
      renderPanel();

      await waitFor(() => expect(getEvaluation).toHaveBeenCalled());
      expect(getEvaluation.mock.calls[0].slice(0, 2)).toEqual([10, "sparse"]);
    });

    it("defaults to dense at top-5 when the URL says nothing", async () => {
      renderPanel();

      await waitFor(() => expect(getEvaluation).toHaveBeenCalled());
      expect(getEvaluation.mock.calls[0].slice(0, 2)).toEqual([5, "dense"]);
    });

    it("re-runs when the retriever changes", async () => {
      renderPanel();
      await screen.findByText("What is ACID?");

      await userEvent.selectOptions(screen.getByLabelText(/retriever/i), "hybrid");

      expect(replace).toHaveBeenCalledWith("/evaluation?retriever=hybrid");
    });

    it("commits top-K on Enter rather than per keystroke", async () => {
      // Each commit re-runs retrieval over the whole labelled dataset, so
      // typing "12" per keystroke would first run the entire thing at K=1.
      renderPanel();
      await screen.findByText("What is ACID?");

      const input = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(input);
      await userEvent.type(input, "12");
      expect(replace).not.toHaveBeenCalled();

      await userEvent.type(input, "{Enter}");
      expect(replace).toHaveBeenCalledWith("/evaluation?top_k=12");
    });

    it("clamps a top-K the API would refuse", async () => {
      renderPanel();
      await screen.findByText("What is ACID?");

      const input = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(input);
      await userEvent.type(input, "500{Enter}");

      expect(replace).toHaveBeenCalledWith("/evaluation?top_k=20");
    });
  });

  describe("latency", () => {
    it("reports the tail, not only the mean", async () => {
      // One slow question moves the mean by a little and p95 by a lot, and p95
      // is what someone waiting on a query actually meets.
      renderPanel();

      expect(await screen.findByText("p95 latency")).toBeInTheDocument();
      expect(screen.getByText("170 ms")).toBeInTheDocument();
    });

    it("still shows the mean, for comparison with the tail", async () => {
      renderPanel();
      expect(await screen.findByText("Mean latency")).toBeInTheDocument();
    });
  });

  describe("failures", () => {
    it("names the questions that retrieved nothing relevant", async () => {
      // A hit rate of 0.96 over 53 questions is two failures, and those two
      // are the only ones worth reading.
      renderPanel();

      expect(
        await screen.findByText(/1 question retrieved nothing relevant/i),
      ).toBeInTheDocument();
    });

    it("says so plainly when nothing failed", async () => {
      getEvaluation.mockResolvedValue({
        ...RESPONSE,
        questions: RESPONSE.questions.map((q) => ({ ...q, hit: true })),
      });
      renderPanel();

      expect(
        await screen.findByText(/Every question retrieved at least one relevant chunk/i),
      ).toBeInTheDocument();
    });
  });

  describe("views", () => {
    it("shows only the missed questions when asked", async () => {
      searchParams = new URLSearchParams("?view=missed");
      renderPanel();

      const table = await screen.findByRole("table");
      expect(within(table).getByText("What is a deadlock?")).toBeInTheDocument();
      expect(within(table).queryByText("What is ACID?")).toBeNull();
    });

    it("puts the worst-ranked question first", async () => {
      searchParams = new URLSearchParams("?view=worst");
      renderPanel();

      await screen.findByText("What is ACID?");
      const body = within(screen.getByRole("table")).getAllByRole("row").slice(1);
      expect(within(body[0]).getByText("What is a deadlock?")).toBeInTheDocument();
    });

    it("does not reorder the cached response itself", async () => {
      // sort mutates, and this array belongs to the query cache: sorting in
      // place would leave every other view permanently reordered.
      searchParams = new URLSearchParams("?view=worst");
      renderPanel();
      await screen.findByText("What is ACID?");

      expect(RESPONSE.questions[0].question).toBe("What is ACID?");
    });
  });
});
