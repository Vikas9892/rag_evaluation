import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "./settings-panel";
import type { ConfigResponse } from "@/types/api";

const getConfig = vi.hoisted(() => vi.fn());
vi.mock("@/services/api", () => ({ getConfig }));

const CONFIG: ConfigResponse = {
  embedding_model: "BAAI/bge-small-en-v1.5",
  llm_model: "llama-3.1-8b-instant",
  llm_temperature: 0,
  llm_max_tokens: 1024,
  chunk_size: 250,
  chunk_overlap: 50,
  min_chunk_chars: 50,
  default_top_k: 5,
  max_context_chunks: 5,
  retrievers: ["dense", "sparse", "hybrid"],
  indexed_chunks: 148,
  documents: 8,
  reranker_enabled: false,
  reranker_available: true,
  default_retriever: "dense",
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<SettingsPanel />, { wrapper: Wrapper });
}

beforeEach(() => {
  getConfig.mockReset().mockResolvedValue(CONFIG);
});

describe("SettingsPanel", () => {
  it("reports the deployment's models rather than a hardcoded name", async () => {
    // A page listing the model from a TypeScript constant would describe the
    // frontend's belief about the deployment, not the deployment.
    renderPanel();

    expect(await screen.findByText("BAAI/bge-small-en-v1.5")).toBeInTheDocument();
    expect(screen.getByText("llama-3.1-8b-instant")).toBeInTheDocument();
  });

  it("reports the indexed corpus it actually loaded", async () => {
    renderPanel();
    expect(await screen.findByText("148 from 8 documents")).toBeInTheDocument();
  });

  describe("the reranker's status", () => {
    it("says it is available and off, not that it is missing", async () => {
      // It runs when a query asks for it. Calling that "not in the live path"
      // describes a state this deployment left behind.
      renderPanel();

      expect(await screen.findByText("available, off by default")).toBeInTheDocument();
    });

    it("says what turning it on costs", async () => {
      renderPanel();
      expect(await screen.findByText(/hundreds of milliseconds/)).toBeInTheDocument();
    });

    it("says so plainly when it is on by default", async () => {
      getConfig.mockResolvedValue({ ...CONFIG, reranker_enabled: true });
      renderPanel();

      expect(await screen.findByText("on by default")).toBeInTheDocument();
    });

    it("says so when the model could not be loaded at all", async () => {
      getConfig.mockResolvedValue({
        ...CONFIG,
        reranker_enabled: false,
        reranker_available: false,
      });
      renderPanel();

      expect(await screen.findByText("not available")).toBeInTheDocument();
    });
  });

  it("points retrieval settings at the query page, where a link can carry them", async () => {
    renderPanel();
    expect(await screen.findByRole("link", { name: /query page/i })).toHaveAttribute(
      "href",
      "/query",
    );
  });

  it("surfaces a failure instead of rendering an empty deployment", async () => {
    getConfig.mockRejectedValue(new Error("offline"));
    renderPanel();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("llama-3.1-8b-instant")).toBeNull();
  });
});
