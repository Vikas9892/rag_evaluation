import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkspacePanel } from "./workspace-panel";
import { ApiError } from "@/services/api-error";
import type { DocumentResponse } from "@/types/api";

const getDocuments = vi.hoisted(() => vi.fn());
const uploadDocument = vi.hoisted(() => vi.fn());
const deleteDocument = vi.hoisted(() => vi.fn());
const getQueueStatus = vi.hoisted(() => vi.fn());
const getCorpora = vi.hoisted(() => vi.fn());

vi.mock("@/services/api", () => ({
  getDocuments,
  uploadDocument,
  deleteDocument,
  getQueueStatus,
  getCorpora,
}));

function doc(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    document_id: "d1",
    corpus_id: "workspace",
    filename: "handbook.pdf",
    content_type: "application/pdf",
    size_bytes: 2_400_000,
    status: "READY",
    progress: 1,
    chunk_count: 148,
    error: null,
    created_at: "2026-08-16T00:00:00+00:00",
    updated_at: "2026-08-16T00:00:05+00:00",
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<WorkspacePanel />, { wrapper: Wrapper });
}

function file(name = "notes.md", size = 1024, type = "text/markdown"): File {
  const f = new File(["x".repeat(Math.min(size, 1024))], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

/** Drop a file on the zone, which is how an unsupported type actually arrives. */
function drop(...files: File[]) {
  const zone = screen.getByText(/Drop documents here/).closest("div")!;
  fireEvent.drop(zone, { dataTransfer: { files, types: ["Files"] } });
}

beforeEach(() => {
  getDocuments.mockReset().mockResolvedValue({ documents: [] });
  uploadDocument.mockReset().mockResolvedValue({ document_id: "new", job_id: "j" });
  deleteDocument.mockReset().mockResolvedValue({ deleted: true });
  getQueueStatus.mockReset().mockResolvedValue({
    backend: "in-process",
    durable: false,
    workers: 1,
    note: "inline",
  });
  getCorpora.mockReset().mockResolvedValue({ corpora: [] });
});

describe("WorkspacePanel", () => {
  it("invites an upload when the corpus is empty", async () => {
    renderPanel();
    expect(await screen.findByText(/No documents yet/)).toBeInTheDocument();
  });

  it("lists documents with their size and chunk count", async () => {
    getDocuments.mockResolvedValue({ documents: [doc()] });
    renderPanel();

    expect(await screen.findByText("handbook.pdf")).toBeInTheDocument();
    expect(screen.getByText(/2.3 MB · 148 chunks/)).toBeInTheDocument();
  });

  it("states the accepted formats and the size limit up front", async () => {
    renderPanel();
    expect(await screen.findByText(/\.pdf, \.txt, \.md/)).toBeInTheDocument();
    expect(screen.getByText(/up to 25 MB each/)).toBeInTheDocument();
  });

  describe("indexing progress", () => {
    it("shows the worker's stages while a document is indexing", async () => {
      getDocuments.mockResolvedValue({ documents: [doc({ status: "EMBEDDING" })] });
      renderPanel();

      await screen.findByText("handbook.pdf");
      for (const stage of ["Uploaded", "Parsed", "Chunked", "Embedded"]) {
        expect(screen.getByText(stage)).toBeInTheDocument();
      }
    });

    it("hides the stage list once a document is ready", async () => {
      // Six ticks on every finished document turns the list into noise.
      getDocuments.mockResolvedValue({ documents: [doc({ status: "READY" })] });
      renderPanel();

      await screen.findByText("handbook.pdf");
      expect(screen.queryByText("Embedded")).not.toBeInTheDocument();
    });

    it("offers to query only a document that is ready", async () => {
      getDocuments.mockResolvedValue({ documents: [doc({ status: "EMBEDDING" })] });
      renderPanel();

      await screen.findByText("handbook.pdf");
      expect(
        screen.queryByRole("link", { name: /ask questions/i }),
      ).not.toBeInTheDocument();
    });

    it("links a ready document to the query page for its corpus", async () => {
      getDocuments.mockResolvedValue({ documents: [doc()] });
      renderPanel();

      const link = await screen.findByRole("link", { name: /ask questions/i });
      expect(link).toHaveAttribute("href", "/query?corpus=workspace");
    });

    it("reports the status in words, not only by colour", async () => {
      getDocuments.mockResolvedValue({ documents: [doc({ status: "READY" })] });
      renderPanel();
      expect(await screen.findByText("READY")).toBeInTheDocument();
    });
  });

  describe("failures", () => {
    it("shows why a document failed", async () => {
      getDocuments.mockResolvedValue({
        documents: [
          doc({ status: "FAILED", error: "No text could be extracted — needs OCR." }),
        ],
      });
      renderPanel();

      expect(await screen.findByRole("alert")).toHaveTextContent("needs OCR");
    });

    it("surfaces an upload failure with a retry", async () => {
      uploadDocument.mockRejectedValue(new ApiError("network", "offline"));
      renderPanel();

      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      await userEvent.upload(input, file());

      expect(await screen.findByRole("alert")).toBeInTheDocument();
    });
  });

  describe("client-side validation", () => {
    // The file picker filters by the input's accept attribute, so an
    // unsupported type can only arrive by drag and drop. That is the path
    // these exercise, because it is the one a user can actually reach.
    it("rejects a file type with no parser before uploading it", async () => {
      renderPanel();
      drop(file("malware.exe", 1024, "application/octet-stream"));

      expect(await screen.findByRole("alert")).toHaveTextContent("no parser");
      expect(uploadDocument).not.toHaveBeenCalled();
    });

    it("rejects an oversized file before uploading it", async () => {
      renderPanel();
      drop(file("huge.pdf", 30 * 1024 * 1024, "application/pdf"));

      expect(await screen.findByRole("alert")).toHaveTextContent("over the limit");
      expect(uploadDocument).not.toHaveBeenCalled();
    });

    it("rejects an empty file", async () => {
      renderPanel();
      drop(file("blank.md", 0));

      expect(await screen.findByRole("alert")).toHaveTextContent("empty");
      expect(uploadDocument).not.toHaveBeenCalled();
    });

    it("accepts a dropped file the parsers support", async () => {
      renderPanel();
      drop(file("notes.md"));

      await waitFor(() => expect(uploadDocument).toHaveBeenCalled());
    });

    it("uploads a valid file", async () => {
      renderPanel();
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      await userEvent.upload(input, file("notes.md"));

      await waitFor(() => expect(uploadDocument).toHaveBeenCalled());
      expect(uploadDocument.mock.calls[0][1]).toBe("workspace");
    });
  });

  describe("indexing settings", () => {
    it("keeps them behind a disclosure rather than beside the drop zone", async () => {
      renderPanel();
      expect(screen.queryByLabelText(/chunk size/i)).not.toBeInTheDocument();

      await userEvent.click(
        screen.getByRole("button", { name: /show indexing settings/i }),
      );
      expect(screen.getByLabelText(/chunk size/i)).toBeInTheDocument();
    });

    it("says that chunk size applies only to new documents", async () => {
      // The alternative is a user changing it and wondering why nothing
      // already uploaded changed.
      renderPanel();
      await userEvent.click(
        screen.getByRole("button", { name: /show indexing settings/i }),
      );

      expect(
        screen.getByText(/does not re-chunk anything already here/i),
      ).toBeInTheDocument();
    });

    it("passes the chosen chunk size to the upload", async () => {
      renderPanel();
      await userEvent.click(
        screen.getByRole("button", { name: /show indexing settings/i }),
      );
      await userEvent.type(screen.getByLabelText(/chunk size/i), "500");

      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      await userEvent.upload(input, file("notes.md"));

      await waitFor(() => expect(uploadDocument).toHaveBeenCalled());
      expect(uploadDocument.mock.calls[0][2]).toMatchObject({ chunkSize: 500 });
    });
  });

  describe("queue transparency", () => {
    it("says when the queue is not durable", async () => {
      // A spinner that implies durability it does not have is how an upload
      // gets silently lost.
      renderPanel();
      expect(await screen.findByText(/not queued durably/i)).toBeInTheDocument();
    });

    it("says nothing when the queue is durable", async () => {
      getQueueStatus.mockResolvedValue({
        backend: "redis",
        durable: true,
        workers: 1,
        note: "redis",
      });
      renderPanel();

      await screen.findByText(/No documents yet/);
      expect(screen.queryByText(/not queued durably/i)).not.toBeInTheDocument();
    });
  });

  describe("deletion", () => {
    it("deletes a document", async () => {
      getDocuments.mockResolvedValue({ documents: [doc()] });
      renderPanel();

      await userEvent.click(
        await screen.findByRole("button", { name: /delete handbook/i }),
      );
      await waitFor(() => expect(deleteDocument).toHaveBeenCalledWith("d1"));
    });
  });
});
