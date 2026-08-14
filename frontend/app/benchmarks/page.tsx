import { PendingPanel } from "@/components/pending-panel";
import { PageHeader } from "@/components/layout/page-header";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/benchmarks");

export default function BenchmarksPage() {
  const { title, description } = routeMeta("/benchmarks");

  return (
    <>
      <PageHeader title={title} description={description} />
      <PendingPanel milestone="Milestone 15">
        A comparison matrix across chunk size, top-K and retriever, with charts.
        Meaningful comparison needs a larger corpus first: at 19 chunks and 15 questions,
        MRR is already 1.00, so every configuration scores the same and the matrix would
        discriminate nothing.
      </PendingPanel>
    </>
  );
}
