import { PageHeader } from "@/components/layout/page-header";
import { EvaluationPanel } from "@/components/evaluation/evaluation-panel";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/evaluation");

export default function Page() {
  const { title, description } = routeMeta("/evaluation");

  return (
    <>
      <PageHeader title={title} description={description} />
      <EvaluationPanel />
    </>
  );
}
