import { PageHeader } from "@/components/layout/page-header";
import { WorkspacePanel } from "@/components/workspace/workspace-panel";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/workspace");

export default function WorkspacePage() {
  const { title, description } = routeMeta("/workspace");

  return (
    <>
      <PageHeader title={title} description={description} />
      <WorkspacePanel />
    </>
  );
}
