import { PendingPanel } from "@/components/pending-panel";
import { PageHeader } from "@/components/layout/page-header";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/evaluation");

export default function EvaluationPage() {
  const { title, description } = routeMeta("/evaluation");

  return (
    <>
      <PageHeader title={title} description={description} />
      <PendingPanel milestone="Milestones 13–14">
        Precision@K, Recall, Hit Rate and MRR over the 15-question labelled dataset, plus
        per-question results. These metrics belong here and not on the Query page: they
        are undefined without ground truth, and an ad-hoc question has none.
      </PendingPanel>
    </>
  );
}
