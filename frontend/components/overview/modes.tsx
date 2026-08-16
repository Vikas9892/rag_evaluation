"use client";

import { ArrowRightIcon, FlaskConicalIcon, FolderOpenIcon } from "lucide-react";
import Link from "next/link";

import { useCorpora } from "@/hooks/use-documents";
import { CORPUS_DEFAULT } from "@/lib/query-params";

/**
 * The two things this platform is for.
 *
 * The overview used to open with dependency checks and a chunk count — an
 * operations dashboard for someone who already knew what the product was.
 * Anyone arriving without that context could not tell from this page that
 * there are two modes, or which one they wanted.
 *
 * Both run the same retrieval pipeline. That is the claim worth making up
 * front, because it is what makes the benchmark numbers mean anything about
 * the documents a user uploads.
 */
export function Modes() {
  const { data } = useCorpora();

  const uploaded = (data?.corpora ?? []).filter((c) => !c.is_evaluation);
  const uploadedChunks = uploaded.reduce((total, c) => total + c.chunks, 0);
  const benchmark = (data?.corpora ?? []).find((c) => c.is_evaluation);

  return (
    <section aria-labelledby="modes-heading">
      <h2 id="modes-heading" className="sr-only">
        What you can do here
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <ModeCard
          href="/workspace"
          icon={FolderOpenIcon}
          title="Workspace"
          lead="Upload your own documents and ask questions of them."
          detail="Parsed, chunked, embedded and indexed on a worker. The page keeps working while that happens, and every answer shows the chunks it came from."
          // Named rather than described: "3 documents" tells a returning user
          // whether their corpus survived the restart.
          status={
            uploaded.length > 0
              ? `${uploaded.length} ${uploaded.length === 1 ? "corpus" : "corpora"}, ${uploadedChunks} chunks indexed`
              : "Nothing uploaded yet"
          }
        />
        <ModeCard
          href="/evaluation"
          icon={FlaskConicalIcon}
          title="Evaluation Lab"
          lead="Measure whether the retrieval is any good, and which settings are better."
          detail="Precision@K, Recall, MRR and hit rate over a labelled dataset, per-question failures, and a benchmark matrix across retrievers and top-K."
          status={
            benchmark
              ? `Benchmark corpus ${benchmark.ready ? "indexed" : "not built"}`
              : `Corpus "${CORPUS_DEFAULT}"`
          }
        />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">
        Both modes run the same retrieval pipeline over different corpora — the benchmark
        numbers describe the code that answers your uploads, not a separate demo path.
      </p>
    </section>
  );
}

function ModeCard({
  href,
  icon: Icon,
  title,
  lead,
  detail,
  status,
}: {
  href: string;
  icon: typeof FolderOpenIcon;
  title: string;
  lead: string;
  detail: string;
  status: string;
}) {
  return (
    <Link
      href={href}
      className="border-border hover:bg-accent focus-visible:ring-ring group rounded-lg border p-5 transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <span className="flex items-center gap-2 text-base font-medium">
        <Icon aria-hidden className="size-4" />
        {title}
        <ArrowRightIcon
          aria-hidden
          className="size-4 opacity-0 transition-opacity group-hover:opacity-60"
        />
      </span>
      <span className="mt-2 block text-sm">{lead}</span>
      <span className="text-muted-foreground mt-1 block text-sm">{detail}</span>
      <span className="text-muted-foreground mt-3 block font-mono text-xs">{status}</span>
    </Link>
  );
}
