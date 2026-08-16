import { ExternalLinkIcon } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { MeasuredQuality } from "@/components/about/measured-quality";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/about");

/** What each layer is actually built on. Kept short: a stack list is a fact. */
const STACK = [
  { area: "Frontend", tools: "Next.js 16 · React 19 · TanStack Query · Tailwind" },
  { area: "API", tools: "FastAPI · Pydantic · SSE streaming" },
  { area: "Retrieval", tools: "FAISS · BM25 (rank-bm25) · Reciprocal Rank Fusion" },
  { area: "Models", tools: "bge-small-en-v1.5 · ms-marco-MiniLM-L-6 · llama-3.1-8b" },
  { area: "Storage", tools: "SQLite (documents) · numpy vectors · JSON metadata" },
  { area: "Worker", tools: "In-process thread, or Redis when configured" },
];

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
          <h2 className="text-foreground mb-2 text-[13px] font-semibold tracking-wide uppercase">
            What this is
          </h2>
          <p className="text-muted-foreground">
            An engineering platform for building, evaluating and benchmarking
            Retrieval-Augmented Generation systems &mdash; not a chatbot. A chatbot
            answers questions; this answers whether the retrieval behind those answers is
            any good, and how you know.
          </p>
        </section>

        <section>
          <h2 className="text-foreground mb-3 text-[13px] font-semibold tracking-wide uppercase">
            Pipeline
          </h2>
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
          <h2 className="text-foreground mb-3 text-[13px] font-semibold tracking-wide uppercase">
            Measured quality
          </h2>
          {/*
            Read from the API, never typed here. The section below argues that a
            fabricated metric is exactly what this product exists to prevent,
            and a hardcoded list on this page had already drifted to claiming
            Recall 1.00 over a dataset that had since more than tripled.
          */}
          <MeasuredQuality />
        </section>

        <section>
          <h2 className="text-foreground mb-2 text-[13px] font-semibold tracking-wide uppercase">
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
          <h2 className="text-foreground mb-2 text-[13px] font-semibold tracking-wide uppercase">
            Ground truth
          </h2>
          <p className="text-muted-foreground">
            Evaluation labels are anchored to content spans, not to chunk IDs. Chunk IDs
            are a function of chunk size and separators, so re-chunking silently re-points
            every label at different text &mdash; once moving MRR from 1.000 to 0.143 with
            no error raised anywhere. Each span is now resolved against the live index at
            evaluation time and must match exactly one chunk, so a stale label fails the
            build instead of corrupting a number.
          </p>
        </section>
        <section>
          <h2 className="text-foreground mb-3 text-[13px] font-semibold tracking-wide uppercase">
            Built with
          </h2>
          <dl className="border-border divide-border grid divide-y rounded-lg border">
            {STACK.map((row) => (
              <div
                key={row.area}
                className="grid gap-1 px-4 py-2.5 sm:grid-cols-[9rem_1fr]"
              >
                <dt className="text-muted-foreground text-[13px]">{row.area}</dt>
                <dd className="font-mono text-[13px]">{row.tools}</dd>
              </div>
            ))}
          </dl>
          <p className="text-subtle-foreground mt-3 text-xs">
            No LangChain and no framework abstractions: every stage above is written
            directly, which is what makes the trace on the Query page able to report what
            each one actually did.
          </p>
        </section>

        <section className="border-border flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-5">
          <span className="font-mono text-xs">v1.1</span>
          <a
            href="https://github.com/Vikas9892/rag_evaluation"
            className="text-info inline-flex items-center gap-1.5 text-[13px] underline decoration-dotted underline-offset-4"
            target="_blank"
            rel="noreferrer noopener"
          >
            <ExternalLinkIcon aria-hidden className="size-3.5" />
            Source on GitHub
          </a>
          <span className="text-subtle-foreground text-xs">
            Metrics on this deployment are retrieval-only; generation quality is not
            measured.
          </span>
        </section>
      </div>
    </>
  );
}
