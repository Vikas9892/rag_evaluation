import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryPanel } from "./query-panel";
import { ApiError } from "@/services/api-error";
import type { StreamEvent } from "@/types/api";

const push = vi.fn();
const replace = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/query",
  useSearchParams: () => searchParams,
}));

const streamQuery = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ streamQuery }));

const DONE = {
  request_id: "3f8a1c20-d42b-4e7e-9b5f-abcdef012345",
  retriever: "hybrid" as const,
  retrieval_latency_ms: 4.2,
  generation_latency_ms: 1183,
  total_latency_ms: 1187.2,
  first_token_latency_ms: 210.5,
  pipeline: [
    { name: "embedding" as const, status: "ok" as const, latency_ms: 381.33 },
    {
      name: "dense" as const,
      status: "ok" as const,
      latency_ms: 2.61,
      candidates_in: 19,
      candidates_out: 12,
    },
    {
      name: "sparse" as const,
      status: "ok" as const,
      latency_ms: 0.38,
      candidates_in: 19,
      candidates_out: 2,
    },
    {
      name: "fusion" as const,
      status: "ok" as const,
      latency_ms: 0.05,
      candidates_in: 12,
      candidates_out: 3,
    },
    { name: "reranker" as const, status: "skipped" as const, latency_ms: 0 },
    {
      name: "generation" as const,
      status: "ok" as const,
      latency_ms: 603.07,
      candidates_in: 3,
    },
  ],
};

const ANSWER = "ACID is atomicity, consistency, isolation, durability.";

const FULL_STREAM: StreamEvent[] = [
  {
    type: "sources",
    data: [
      {
        document_id: "dbms.md",
        chunk_id: "dbms.md_0",
        score: 0.0323,
        rank: 1,
        text: "ACID guarantees atomicity, consistency, isolation and durability.",
        metadata: { heading: "ACID" },
        scores: {
          dense: { score: 0.56, rank: 2 },
          // Sparse did not surface this chunk. Not a zero score — an absence.
          sparse: null,
          fused: { score: 0.0323, rank: 1 },
          reranker: null,
        },
      },
    ],
  },
  { type: "token", data: "ACID is atomicity, " },
  { type: "token", data: "consistency, isolation, durability." },
  { type: "done", data: DONE },
];

/** Turns a fixed event list into the async generator streamQuery returns. */
function emits(events: StreamEvent[]) {
  return async function* () {
    for (const event of events) yield event;
  };
}

/** A stream that yields, then throws — the mid-generation failure case. */
function emitsThenThrows(events: StreamEvent[], error: unknown) {
  return async function* () {
    for (const event of events) yield event;
    throw error;
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<QueryPanel />, { wrapper: Wrapper });
}

beforeEach(() => {
  searchParams = new URLSearchParams();
  window.localStorage.clear();
  streamQuery.mockReset();
  streamQuery.mockImplementation(emits(FULL_STREAM));
  push.mockReset();
  replace.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("QueryPanel", () => {
  it("asks nothing until there is a question in the URL", () => {
    renderPanel();

    expect(screen.getByText(/no question yet/i)).toBeInTheDocument();
    expect(streamQuery).not.toHaveBeenCalled();
  });

  it("answers the question already in the URL, so a shared link works on arrival", async () => {
    searchParams = new URLSearchParams("?q=what+is+ACID");

    renderPanel();

    expect(await screen.findByText(ANSWER)).toBeInTheDocument();
    expect(streamQuery).toHaveBeenCalledWith(
      "what is ACID",
      5,
      expect.anything(),
      "hybrid",
    );
  });

  it("honours a non-default top_k from the URL", async () => {
    searchParams = new URLSearchParams("?q=hello&top_k=12");

    renderPanel();

    await waitFor(() =>
      expect(streamQuery).toHaveBeenCalledWith("hello", 12, expect.anything(), "hybrid"),
    );
  });

  describe("streaming", () => {
    it("assembles the tokens into one answer", async () => {
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      // Neither token is a standalone text node once joined.
      expect(await screen.findByText(ANSWER)).toBeInTheDocument();
    });

    it("shows text that has arrived before the stream finishes", async () => {
      // The point of streaming: something readable before the answer is whole.
      searchParams = new URLSearchParams("?q=hello");
      let release!: () => void;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      streamQuery.mockImplementation(async function* () {
        yield { type: "token", data: "partial text" } as StreamEvent;
        await gate;
        yield { type: "done", data: DONE } as StreamEvent;
      });

      renderPanel();

      expect(await screen.findByText("partial text")).toBeInTheDocument();
      // Still mid-stream, so no closing metrics yet.
      expect(screen.queryByText(/ms total/)).not.toBeInTheDocument();

      release();
      expect(await screen.findByText(/ms total/)).toBeInTheDocument();
    });

    it("reports latency and time to first token once complete", async () => {
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      const metrics = await screen.findByText(/ms total/);
      expect(metrics).toHaveTextContent("1187 ms total");
      expect(metrics).toHaveTextContent("211 ms to first token");
      expect(metrics).toHaveTextContent("3f8a1c20");
    });

    it("omits time to first token when the model produced none", async () => {
      searchParams = new URLSearchParams("?q=hello");
      streamQuery.mockImplementation(
        emits([{ type: "done", data: { ...DONE, first_token_latency_ms: null } }]),
      );

      renderPanel();

      const metrics = await screen.findByText(/ms total/);
      expect(metrics).not.toHaveTextContent("to first token");
    });
  });

  describe("failure part-way through", () => {
    it("keeps the partial answer and reports the failure beside it", async () => {
      // Replacing what the user is reading with an error throws away the half
      // that worked.
      searchParams = new URLSearchParams("?q=hello");
      streamQuery.mockImplementation(
        emitsThenThrows(
          [{ type: "token", data: "half an answer" }],
          new ApiError("server", "upstream died"),
        ),
      );

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("half an answer")).toBeInTheDocument();
    });

    it("treats a server error event as a failure", async () => {
      searchParams = new URLSearchParams("?q=hello");
      streamQuery.mockImplementation(
        emits([
          { type: "token", data: "started" },
          { type: "error", data: "Internal server error" },
        ]),
      );

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("started")).toBeInTheDocument();
    });

    it("does not present a truncated answer as a finished one", async () => {
      // The connection ended without 'done'. Silently succeeding here would
      // show half an answer with no indication it is half.
      searchParams = new URLSearchParams("?q=hello");
      streamQuery.mockImplementation(emits([{ type: "token", data: "cut off" }]));

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("cut off")).toBeInTheDocument();
      expect(screen.queryByText(/ms total/)).not.toBeInTheDocument();
    });

    it("explains a 503 and offers no retry", async () => {
      searchParams = new URLSearchParams("?q=hello");
      streamQuery.mockImplementation(() => {
        throw new ApiError("unavailable", "no index", {
          status: 503,
          detail: "FAISS index not built",
        });
      });

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/FAISS index not built/)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /try again/i }),
      ).not.toBeInTheDocument();
    });

    it("offers a retry for a network failure and re-runs the request", async () => {
      searchParams = new URLSearchParams("?q=hello");
      streamQuery
        .mockImplementationOnce(() => {
          throw new ApiError("network", "offline");
        })
        .mockImplementationOnce(emits(FULL_STREAM));

      renderPanel();

      await userEvent.click(await screen.findByRole("button", { name: /try again/i }));

      expect(await screen.findByText(ANSWER)).toBeInTheDocument();
    });
  });

  describe("navigation", () => {
    it("pushes the question so Back returns to the previous one", async () => {
      renderPanel();

      await userEvent.type(
        screen.getByRole("combobox", { name: "Question" }),
        "what is a deadlock{Enter}",
      );

      expect(push).toHaveBeenCalledWith("/query?q=what+is+a+deadlock");
    });

    it("replaces rather than pushes when a setting changes", async () => {
      // Pushing would make Back walk through every intermediate top-K value.
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.type(topK, "8{Enter}");

      await waitFor(() => expect(replace).toHaveBeenCalled());
      expect(push).not.toHaveBeenCalled();
      expect(replace).toHaveBeenLastCalledWith("/query?q=hello&top_k=8");
    });

    it("commits top-K once, not once per keystroke", async () => {
      // Each commit is a navigation, a refetch and a Groq call. Typing "12"
      // must not first ask the question with top_k=1.
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.type(topK, "12");
      expect(replace).not.toHaveBeenCalled();

      await userEvent.tab();

      expect(replace).toHaveBeenCalledOnce();
      expect(replace).toHaveBeenCalledWith("/query?q=hello&top_k=12");
    });

    it("restores the current value when the box is left empty", async () => {
      searchParams = new URLSearchParams("?q=hello&top_k=7");
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.tab();

      expect(topK).toHaveValue(7);
      expect(replace).not.toHaveBeenCalled();
    });

    it("clamps a typed value that exceeds what the API accepts", async () => {
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.type(topK, "500{Enter}");

      expect(replace).toHaveBeenCalledWith("/query?q=hello&top_k=20");
    });

    it("sends the retriever chosen in the URL", async () => {
      searchParams = new URLSearchParams("?q=hello&retriever=sparse");
      renderPanel();

      await waitFor(() =>
        expect(streamQuery).toHaveBeenCalledWith("hello", 5, expect.anything(), "sparse"),
      );
    });

    it("replaces the URL when the retriever changes", async () => {
      searchParams = new URLSearchParams("?q=hello");
      renderPanel();

      await userEvent.selectOptions(screen.getByLabelText(/retriever/i), "dense");

      expect(replace).toHaveBeenCalledWith("/query?q=hello&retriever=dense");
      expect(push).not.toHaveBeenCalled();
    });

    it("keeps top_k when the retriever changes", async () => {
      // Both settings live in one URL; changing either must not drop the other.
      searchParams = new URLSearchParams("?q=hello&top_k=12");
      renderPanel();

      await userEvent.selectOptions(screen.getByLabelText(/retriever/i), "sparse");

      expect(replace).toHaveBeenCalledWith("/query?q=hello&top_k=12&retriever=sparse");
    });

    it("remembers the question for future suggestions", async () => {
      renderPanel();

      await userEvent.type(
        screen.getByRole("combobox", { name: "Question" }),
        "remember me{Enter}",
      );

      expect(window.localStorage.getItem("rag-eval.question-history.v1")).toContain(
        "remember me",
      );
    });
  });

  it("clears stored history on request", async () => {
    window.localStorage.setItem(
      "rag-eval.question-history.v1",
      JSON.stringify(["an old question"]),
    );
    renderPanel();

    await userEvent.click(await screen.findByRole("button", { name: /clear history/i }));

    expect(window.localStorage.getItem("rag-eval.question-history.v1")).toBeNull();
  });
});
