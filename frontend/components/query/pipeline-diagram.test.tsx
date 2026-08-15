import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PipelineDiagram } from "./pipeline-diagram";
import type { PipelineStage } from "@/types/api";

const FULL: PipelineStage[] = [
  { name: "embedding", status: "ok", latency_ms: 381.33 },
  {
    name: "dense",
    status: "ok",
    latency_ms: 2.61,
    candidates_in: 19,
    candidates_out: 12,
  },
  {
    name: "sparse",
    status: "ok",
    latency_ms: 0.38,
    candidates_in: 19,
    candidates_out: 2,
  },
  {
    name: "fusion",
    status: "ok",
    latency_ms: 0.05,
    candidates_in: 12,
    candidates_out: 3,
  },
  { name: "reranker", status: "skipped", latency_ms: 0 },
  { name: "generation", status: "ok", latency_ms: 603.07, candidates_in: 3 },
];

const stages = () => within(screen.getByRole("list")).getAllByRole("listitem");

describe("PipelineDiagram", () => {
  it("draws every stage in data-flow order", () => {
    render(<PipelineDiagram stages={FULL} />);

    const labels = ["Embedding", "Dense", "BM25", "Fusion", "Reranker", "Generation"];
    const rendered = stages();

    expect(rendered).toHaveLength(labels.length);
    labels.forEach((label, index) => {
      expect(within(rendered[index]).getByText(label)).toBeInTheDocument();
    });
  });

  it("draws a stage that did not run rather than omitting it", () => {
    // A missing reranker reads as "this deployment has none", which is a
    // different claim from "it did not run for this query".
    render(<PipelineDiagram stages={FULL} />);
    expect(screen.getByText("Reranker")).toBeInTheDocument();
  });

  describe("a skipped stage", () => {
    it("says so in words, not only in styling", () => {
      // Dashed and faded is not readable as "did not run" on its own, and
      // disappears entirely in forced-colours mode.
      render(<PipelineDiagram stages={FULL} />);
      expect(screen.getByText("did not run")).toBeInTheDocument();
    });

    it("reports no timing, because its zero is an absence", () => {
      render(<PipelineDiagram stages={FULL} />);
      const reranker = stages()[4];

      expect(within(reranker).queryByText(/ms/)).not.toBeInTheDocument();
      expect(within(reranker).queryByText("0%")).not.toBeInTheDocument();
    });

    it("is excluded from the total", () => {
      render(<PipelineDiagram stages={FULL} />);
      // 5 ran, 1 skipped.
      expect(screen.getByText(/across 5 stages/)).toBeInTheDocument();
    });
  });

  describe("latency", () => {
    it("keeps a sub-millisecond stage visible rather than rounding it away", () => {
      // Fusion really does run in ~0.05 ms; "0 ms" would suggest it did not.
      render(<PipelineDiagram stages={FULL} />);
      expect(screen.getByText(/0\.05 ms/)).toBeInTheDocument();
    });

    it("shows each stage's share of the total", () => {
      render(<PipelineDiagram stages={FULL} />);
      const generation = stages()[5];
      expect(within(generation).getByText(/\(61%\)/)).toBeInTheDocument();
    });

    it("names the dominant stage in words", () => {
      // The finding worth carrying away, stated rather than left to be read
      // off a chart the design system cannot colour safely.
      render(<PipelineDiagram stages={FULL} />);
      const summary = screen.getByText(/accounted for/);

      expect(summary).toHaveTextContent("Generation");
      expect(summary).toHaveTextContent("61%");
    });
  });

  describe("candidate counts", () => {
    it("shows the funnel where it applies", () => {
      render(<PipelineDiagram stages={FULL} />);
      expect(within(stages()[1]).getByText(/19/)).toBeInTheDocument();
      expect(within(stages()[1]).getByText(/12/)).toBeInTheDocument();
    });

    it("omits them where the notion does not apply", () => {
      // A question is not a candidate set, so embedding shows no funnel.
      render(<PipelineDiagram stages={[FULL[0]]} />);
      expect(screen.queryByText("to")).not.toBeInTheDocument();
    });

    it("shows a dash for the half that does not apply", () => {
      // Generation consumes chunks but emits prose, not a shortlist.
      render(<PipelineDiagram stages={[FULL[5]]} />);
      const funnel = screen.getByText("to").parentElement;

      expect(funnel).toHaveTextContent("3");
      expect(funnel).toHaveTextContent("—");
    });
  });

  describe("edge cases", () => {
    it("renders nothing in the summary when no stage ran", () => {
      render(
        <PipelineDiagram
          stages={[{ name: "embedding", status: "skipped", latency_ms: 0 }]}
        />,
      );
      expect(screen.queryByText(/accounted for/)).not.toBeInTheDocument();
    });

    it("marks a failed stage as failed", () => {
      // Modelled but not emitted today; it should still render correctly if the
      // backend ever reports one.
      render(
        <PipelineDiagram
          stages={[{ name: "generation", status: "error", latency_ms: 12 }]}
        />,
      );
      expect(screen.getByText("failed")).toBeInTheDocument();
    });
  });
});
