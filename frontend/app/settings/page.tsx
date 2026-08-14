import { PendingPanel } from "@/components/pending-panel";
import { PageHeader } from "@/components/layout/page-header";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/settings");

export default function SettingsPage() {
  const { title, description } = routeMeta("/settings");

  return (
    <>
      <PageHeader title={title} description={description} />
      <PendingPanel milestone="Milestone 8">
        Top-K, retriever choice and the reranker toggle. These are stored in the URL
        rather than component state, so a result stays reproducible and shareable:{" "}
        <code>/query?q=…&amp;top_k=10&amp;retriever=hybrid</code>.
      </PendingPanel>
    </>
  );
}
