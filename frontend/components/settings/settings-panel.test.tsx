import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "./settings-panel";
import type { ConfigResponse, QueueStatusResponse, SettingsResponse } from "@/types/api";

const getConfig = vi.hoisted(() => vi.fn());
const getSettings = vi.hoisted(() => vi.fn());
const getQueueStatus = vi.hoisted(() => vi.fn());
const getDeepHealth = vi.hoisted(() => vi.fn());

vi.mock("@/services/api", () => ({
  getConfig,
  getSettings,
  getQueueStatus,
  getDeepHealth,
}));

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

/**
 * Shaped like the real `/settings` payload.
 *
 * The page reads the API's own taxonomy — which group a setting is in, whether
 * it is query-time or indexing-time — rather than deciding for itself, so the
 * fixture has to carry those fields for the assertions to mean anything.
 */
const SETTINGS: SettingsResponse = {
  groups: {
    retrieval: [
      {
        key: "retriever",
        label: "Retriever",
        value: "dense",
        scope: "query",
        requires_reindex: false,
        editable_per_request: true,
        note: "dense, sparse or hybrid — chosen per request.",
      },
      {
        key: "reranker",
        label: "Cross-encoder reranker",
        value: "off by default",
        scope: "query",
        requires_reindex: false,
        editable_per_request: true,
        note: "Raises MRR and adds hundreds of milliseconds. Opt in per request.",
      },
    ],
    generation: [
      {
        key: "llm_model",
        label: "Model",
        value: "llama-3.1-8b-instant",
        scope: "generation",
        requires_reindex: false,
        editable_per_request: false,
        note: null,
      },
    ],
    indexing: [
      {
        key: "embedding_model",
        label: "Embedding model",
        value: "BAAI/bge-small-en-v1.5",
        scope: "indexing",
        requires_reindex: true,
        editable_per_request: false,
        note: "Every vector was produced by this model.",
      },
    ],
  },
};

const QUEUE: QueueStatusResponse = {
  backend: "in-process",
  durable: false,
  workers: 1,
  note: "Jobs run on a worker thread.",
  storage_ephemeral: false,
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
  getSettings.mockReset().mockResolvedValue(SETTINGS);
  getQueueStatus.mockReset().mockResolvedValue(QUEUE);
  getDeepHealth.mockReset().mockResolvedValue({ status: "healthy", checks: [] });
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
    expect(await screen.findByText("148 chunks from 8 documents")).toBeInTheDocument();
  });

  describe("when a setting takes effect", () => {
    it("marks an indexing-time setting as needing a rebuild", async () => {
      // The distinction the product exists to keep straight: changing chunk
      // size is a re-index, changing top-K is the next request.
      renderPanel();

      expect(await screen.findByText("requires re-index")).toBeInTheDocument();
    });

    it("marks a query-time setting as per-request instead", async () => {
      renderPanel();

      expect(await screen.findAllByText("per request")).not.toHaveLength(0);
      expect(screen.getAllByText("query-time").length).toBeGreaterThan(0);
    });

    it("takes the taxonomy from the API rather than restating it", async () => {
      // Flip the flag in the payload; the page must follow it.
      getSettings.mockResolvedValue({
        groups: {
          indexing: [
            {
              ...SETTINGS.groups.indexing[0],
              requires_reindex: false,
              scope: "query",
            },
          ],
        },
      });
      renderPanel();

      await screen.findByText("BAAI/bge-small-en-v1.5");
      expect(screen.queryByText("requires re-index")).toBeNull();
    });
  });

  describe("the reranker's status", () => {
    it("says what turning it on costs", async () => {
      renderPanel();
      expect(await screen.findByText(/hundreds of milliseconds/)).toBeInTheDocument();
    });
  });

  describe("infrastructure", () => {
    it("reports a queue that is not durable as not durable", async () => {
      renderPanel();
      expect(await screen.findByText("not durable")).toBeInTheDocument();
    });

    it("warns when uploads will not survive a restart", async () => {
      getQueueStatus.mockResolvedValue({ ...QUEUE, storage_ephemeral: true });
      renderPanel();

      expect(await screen.findByText("temporary")).toBeInTheDocument();
      expect(screen.getByText(/lost when this server restarts/)).toBeInTheDocument();
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
    getSettings.mockRejectedValue(new Error("offline"));
    renderPanel();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("llama-3.1-8b-instant")).toBeNull();
  });
});
