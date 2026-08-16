import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Modes } from "./modes";

const getCorpora = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getCorpora }));

const CORPORA = {
  corpora: [
    {
      corpus_id: "evaluation",
      documents: 0,
      chunks: 0,
      ready: true,
      is_evaluation: true,
    },
    {
      corpus_id: "workspace",
      documents: 2,
      chunks: 148,
      ready: true,
      is_evaluation: false,
    },
  ],
};

function renderModes() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<Modes />, { wrapper: Wrapper });
}

beforeEach(() => {
  getCorpora.mockReset().mockResolvedValue(CORPORA);
});

describe("Modes", () => {
  it("names both modes and links to them", () => {
    // Someone arriving without context could not previously tell from this
    // page that there are two modes, or which one they wanted.
    renderModes();

    expect(screen.getByRole("link", { name: /Workspace/ })).toHaveAttribute(
      "href",
      "/workspace",
    );
    expect(screen.getByRole("link", { name: /Evaluation Lab/ })).toHaveAttribute(
      "href",
      "/evaluation",
    );
  });

  it("says the two modes share one pipeline", async () => {
    // This is what makes the benchmark numbers mean anything about a user's
    // own uploaded documents.
    renderModes();
    expect(await screen.findByText(/same retrieval pipeline/)).toBeInTheDocument();
  });

  it("reports what has actually been uploaded", async () => {
    renderModes();
    expect(await screen.findByText(/1 corpus, 148 chunks indexed/)).toBeInTheDocument();
  });

  it("counts only the corpora a user made, not the benchmark one", async () => {
    // The benchmark corpus is built offline and has no document records, so
    // counting it would report a corpus nobody uploaded.
    renderModes();

    await screen.findByText(/1 corpus, 148 chunks indexed/);
    expect(screen.queryByText(/2 corpora/)).toBeNull();
  });

  it("invites a first upload rather than reporting zero", async () => {
    getCorpora.mockResolvedValue({ corpora: [CORPORA.corpora[0]] });
    renderModes();

    expect(await screen.findByText("Nothing uploaded yet")).toBeInTheDocument();
  });

  it("says when the benchmark corpus has no index", async () => {
    // The evaluation pages cannot produce a number without it, and "not built"
    // explains the failure before it happens.
    getCorpora.mockResolvedValue({
      corpora: [{ ...CORPORA.corpora[0], ready: false }],
    });
    renderModes();

    expect(await screen.findByText(/Benchmark corpus not built/)).toBeInTheDocument();
  });

  it("still renders both modes before the corpus list arrives", () => {
    getCorpora.mockReturnValue(new Promise(() => {}));
    renderModes();

    expect(screen.getByRole("link", { name: /Workspace/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Evaluation Lab/ })).toBeInTheDocument();
  });
});
