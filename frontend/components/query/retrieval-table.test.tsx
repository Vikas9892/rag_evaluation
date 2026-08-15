import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { RetrievalTable } from "./retrieval-table";
import type { SourceInfo } from "@/types/api";

function source(overrides: Partial<SourceInfo> = {}): SourceInfo {
  return {
    document_id: "dbms.md",
    chunk_id: "dbms.md_chunk_0000",
    score: 0.0323,
    rank: 1,
    text: "ACID guarantees atomicity, consistency, isolation and durability.",
    metadata: {},
    scores: {
      dense: { score: 0.5607, rank: 2 },
      sparse: { score: 1.648, rank: 2 },
      fused: { score: 0.0323, rank: 1 },
      reranker: null,
    },
    ...overrides,
  };
}

const rows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);

describe("RetrievalTable", () => {
  it("lists a row per retrieved chunk", () => {
    render(
      <RetrievalTable
        retriever="hybrid"
        sources={[source(), source({ chunk_id: "os.md_chunk_0000", rank: 2 })]}
      />,
    );
    expect(rows()).toHaveLength(2);
  });

  it("shows the final rank, document and chunk id", () => {
    render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
    const row = rows()[0];

    expect(within(row).getByText("1")).toBeInTheDocument();
    expect(within(row).getByText("dbms.md")).toBeInTheDocument();
    expect(within(row).getByText("dbms.md_chunk_0000")).toBeInTheDocument();
  });

  it("shows a heading from metadata when there is one", () => {
    render(
      <RetrievalTable
        retriever="hybrid"
        sources={[source({ metadata: { heading: "ACID" } })]}
      />,
    );
    expect(screen.getByText("ACID")).toBeInTheDocument();
  });

  describe("stage columns", () => {
    it("shows dense, BM25 and fused for a hybrid query", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);

      expect(screen.getByRole("columnheader", { name: "Dense" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "BM25" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Fused" })).toBeInTheDocument();
    });

    it("omits the stages a dense query never runs", () => {
      // A column of blanks would read as "BM25 found nothing", which is a
      // different claim from "BM25 was not asked".
      render(<RetrievalTable retriever="dense" sources={[source()]} />);

      expect(screen.getByRole("columnheader", { name: "Dense" })).toBeInTheDocument();
      expect(
        screen.queryByRole("columnheader", { name: "BM25" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("columnheader", { name: "Fused" }),
      ).not.toBeInTheDocument();
    });

    it("omits the stages a sparse query never runs", () => {
      render(<RetrievalTable retriever="sparse" sources={[source()]} />);

      expect(screen.getByRole("columnheader", { name: "BM25" })).toBeInTheDocument();
      expect(
        screen.queryByRole("columnheader", { name: "Dense" }),
      ).not.toBeInTheDocument();
    });

    it("never shows a reranker column, because it does not run", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      expect(
        screen.queryByRole("columnheader", { name: /rerank/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("a stage that did not retrieve a chunk", () => {
    it("is shown as a dash, not a zero", () => {
      // Zero is a score BM25 really can give. Absence is not a score.
      render(
        <RetrievalTable
          retriever="hybrid"
          sources={[source({ scores: { ...source().scores, sparse: null } })]}
        />,
      );

      expect(screen.getByText("not retrieved by BM25")).toBeInTheDocument();
      expect(screen.queryByText("#0")).not.toBeInTheDocument();
    });

    it("explains itself to assistive technology rather than reading as a dash", () => {
      render(
        <RetrievalTable
          retriever="hybrid"
          sources={[source({ scores: { ...source().scores, dense: null } })]}
        />,
      );
      expect(screen.getByText("not retrieved by Dense")).toBeInTheDocument();
    });
  });

  describe("ranks and scores", () => {
    it("leads with each stage's rank", () => {
      // Ranks are the only part comparable across stages: cosine ~0.56, BM25
      // ~1.65 and an RRF sum ~0.03 cannot be read against each other.
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      const row = rows()[0];

      expect(within(row).getAllByText("#2")).toHaveLength(2);
      expect(within(row).getByText("#1")).toBeInTheDocument();
    });

    it("shows each score in its own units without rescaling", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      const row = rows()[0];

      expect(within(row).getByText("0.561")).toBeInTheDocument();
      expect(within(row).getByText("1.65")).toBeInTheDocument();
      expect(within(row).getByText("0.0323")).toBeInTheDocument();
    });

    it("keeps small fusion scores legible", () => {
      // A fixed 2dp would print an RRF sum as "0.03" and lose the ordering.
      render(
        <RetrievalTable
          retriever="hybrid"
          sources={[
            source({
              scores: { ...source().scores, fused: { score: 0.016393, rank: 3 } },
            }),
          ]}
        />,
      );
      expect(screen.getByText("0.0164")).toBeInTheDocument();
    });
  });

  describe("chunk text", () => {
    it("is shown", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      expect(screen.getByText(/ACID guarantees atomicity/)).toBeInTheDocument();
    });

    it("can be expanded when it is long", async () => {
      const long = "word ".repeat(60);
      render(<RetrievalTable retriever="hybrid" sources={[source({ text: long })]} />);

      const toggle = screen.getByRole("button", { name: "Show more" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");

      await userEvent.click(toggle);
      expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });

    it("offers no toggle for a short chunk", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source({ text: "short" })]} />);
      expect(screen.queryByRole("button", { name: /show/i })).not.toBeInTheDocument();
    });
  });

  describe("caption", () => {
    it("says which retriever produced the rows", () => {
      render(<RetrievalTable retriever="sparse" sources={[source()]} />);
      expect(screen.getByText(/retrieved by/i)).toHaveTextContent("sparse");
    });

    it("explains what a dash means for a hybrid query", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      expect(screen.getByText(/not that it scored zero/i)).toBeInTheDocument();
    });

    it("states that the reranker did not run", () => {
      render(<RetrievalTable retriever="hybrid" sources={[source()]} />);
      expect(screen.getByText(/reranker did not run/i)).toBeInTheDocument();
    });
  });
});
