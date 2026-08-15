import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QueryPanel } from "./query-panel";
import { ApiError } from "@/services/api-error";

const push = vi.fn();
const replace = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/query",
  useSearchParams: () => searchParams,
}));

const postQuery = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ postQuery }));

const ANSWER = {
  answer: "ACID is atomicity, consistency, isolation, durability.",
  sources: [],
  retrieval_latency_ms: 4.2,
  generation_latency_ms: 1183,
  total_latency_ms: 1187.2,
  request_id: "3f8a1c20-d42b-4e7e-9b5f-abcdef012345",
};

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<QueryPanel />, { wrapper: Wrapper });
}

beforeEach(() => {
  searchParams = new URLSearchParams();
  window.localStorage.clear();
  postQuery.mockReset();
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
    expect(postQuery).not.toHaveBeenCalled();
  });

  it("answers the question already in the URL, so a shared link works on arrival", async () => {
    searchParams = new URLSearchParams("?q=what+is+ACID");
    postQuery.mockResolvedValue(ANSWER);

    renderPanel();

    expect(await screen.findByText(ANSWER.answer)).toBeInTheDocument();
    expect(postQuery).toHaveBeenCalledWith("what is ACID", 5, expect.anything());
  });

  it("honours a non-default top_k from the URL", async () => {
    searchParams = new URLSearchParams("?q=hello&top_k=12");
    postQuery.mockResolvedValue(ANSWER);

    renderPanel();

    await waitFor(() =>
      expect(postQuery).toHaveBeenCalledWith("hello", 12, expect.anything()),
    );
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
      postQuery.mockResolvedValue(ANSWER);
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
      postQuery.mockResolvedValue(ANSWER);
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
      postQuery.mockResolvedValue(ANSWER);
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.tab();

      expect(topK).toHaveValue(7);
      expect(replace).not.toHaveBeenCalled();
    });

    it("clamps a typed value that exceeds what the API accepts", async () => {
      searchParams = new URLSearchParams("?q=hello");
      postQuery.mockResolvedValue(ANSWER);
      renderPanel();

      const topK = screen.getByLabelText(/chunks retrieved/i);
      await userEvent.clear(topK);
      await userEvent.type(topK, "500{Enter}");

      expect(replace).toHaveBeenCalledWith("/query?q=hello&top_k=20");
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

  describe("failure", () => {
    it("explains a 503 and offers no retry", async () => {
      searchParams = new URLSearchParams("?q=hello");
      postQuery.mockRejectedValue(
        new ApiError("unavailable", "no index", {
          status: 503,
          detail: "FAISS index not built",
        }),
      );

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/FAISS index not built/)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /try again/i }),
      ).not.toBeInTheDocument();
    });

    it("offers a retry for a network failure and re-runs the request", async () => {
      searchParams = new URLSearchParams("?q=hello");
      postQuery.mockRejectedValueOnce(new ApiError("network", "offline"));
      postQuery.mockResolvedValueOnce(ANSWER);

      renderPanel();

      await userEvent.click(await screen.findByRole("button", { name: /try again/i }));

      expect(await screen.findByText(ANSWER.answer)).toBeInTheDocument();
    });

    it("shows the reason rather than a skeleton while retrying", async () => {
      // isFetching goes true again during a retry; a skeleton would hide why
      // the first attempt failed.
      searchParams = new URLSearchParams("?q=hello");
      postQuery.mockRejectedValue(new ApiError("timeout", "slow"));

      renderPanel();

      expect(await screen.findByRole("alert")).toBeInTheDocument();
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
