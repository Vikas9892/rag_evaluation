import { PageHeader } from "@/components/layout/page-header";
import { MeasuredQuality } from "@/components/about/measured-quality";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/about");

const STAGES = [
  { name: "Embedding", detail: "BAAI/bge-small-en-v1.5, 384-dim, CPU" },
  { name: "Dense", detail: "FAISS IndexFlatIP, exact inner-product search" },
  { name: "Sparse", detail: "BM25 over the same chunks" },
  { name: "Fusion", detail: "Reciprocal Rank Fusion, k = 60" },
  {
    name: "Reranker",
    detail: "Cross-encoder ms-marco-MiniLM-L-6-v2 — opt-in per query, off by default",
  },
  { name: "Generation", detail: "Groq llama-3.1-8b-instant, temperature 0" },
];

export default function AboutPage() {
  const { title, description } = routeMeta("/about");

  return (
    <>
      <PageHeader title={title} description={description} />

      <div className="max-w-3xl space-y-8 text-sm leading-relaxed">
        <section>
          <h2 className="mb-2 text-base font-semibold">What this is</h2>
          <p className="text-muted-foreground">
            An engineering platform for building, evaluating and benchmarking
            Retrieval-Augmented Generation systems &mdash; not a chatbot. A chatbot
            answers questions; this answers whether the retrieval behind those answers is
            any good, and how you know.
          </p>
        </section>

        <section>
          <h2 className="mb-3 text-base font-semibold">Pipeline</h2>
          <ol className="border-border divide-border divide-y rounded-lg border">
            {STAGES.map((stage, i) => (
              <li key={stage.name} className="flex gap-3 px-4 py-3">
                <span className="text-muted-foreground w-5 shrink-0 tabular-nums">
                  {i + 1}
                </span>
                <span className="w-28 shrink-0 font-medium">{stage.name}</span>
                <span className="text-muted-foreground">{stage.detail}</span>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="mb-3 text-base font-semibold">Measured quality</h2>
          {/*
            Read from the API, never typed here. The section below argues that a
            fabricated metric is exactly what this product exists to prevent,
            and a hardcoded list on this page had already drifted to claiming
            Recall 1.00 over a dataset that had since more than tripled.
          */}
          <MeasuredQuality />
        </section>

        <section>
          <h2 className="mb-2 text-base font-semibold">
            Why accuracy metrics are not on the Query page
          </h2>
          <p className="text-muted-foreground">
            Precision, Recall and MRR are undefined without ground truth, and a question
            typed a second ago has none. The Query page therefore shows only what is
            directly observable &mdash; scores, latency, tokens, whether dense and sparse
            agreed &mdash; while accuracy lives on the Evaluation page, over the labelled
            dataset. Any Precision@5 rendered next to an ad-hoc answer would be
            fabricated.
          </p>
        </section>

        <section>
          <h2 className="mb-2 text-base font-semibold">Ground truth</h2>
          <p className="text-muted-foreground">
            Evaluation labels are anchored to content spans, not to chunk IDs. Chunk IDs
            are a function of chunk size and separators, so re-chunking silently re-points
            every label at different text &mdash; once moving MRR from 1.000 to 0.143 with
            no error raised anywhere. Each span is now resolved against the live index at
            evaluation time and must match exactly one chunk, so a stale label fails the
            build instead of corrupting a number.
          </p>
        </section>
      </div>
    </>
  );
}
