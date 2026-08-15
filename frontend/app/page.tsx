import { PageHeader } from "@/components/layout/page-header";
import { OverviewPanel } from "@/components/overview/overview-panel";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/");

export default function Page() {
  const { title, description } = routeMeta("/");

  return (
    <>
      <PageHeader title={title} description={description} />
      <OverviewPanel />
    </>
  );
}
