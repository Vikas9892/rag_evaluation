import { PendingPanel } from "@/components/pending-panel";
import { PageHeader } from "@/components/layout/page-header";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/query");

export default function QueryPage() {
  const { title, description } = routeMeta("/query");

  return (
    <>
      <PageHeader title={title} description={description} />
      <PendingPanel milestone="Milestones 6–8">
        Question input, streaming answer and the retrieval trace land here. The
        trace needs per-stage attribution the API does not expose yet:{" "}
        <code>HybridRetriever</code> fuses dense and sparse into a single score
        and discards the component ranks, so the backend contract changes before
        this page can show a Dense/BM25/Final breakdown.
      </PendingPanel>
    </>
  );
}
