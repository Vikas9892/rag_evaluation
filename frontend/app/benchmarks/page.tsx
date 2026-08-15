import { PageHeader } from "@/components/layout/page-header";
import { BenchmarksPanel } from "@/components/benchmarks/benchmarks-panel";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/benchmarks");

export default function Page() {
  const { title, description } = routeMeta("/benchmarks");

  return (
    <>
      <PageHeader title={title} description={description} />
      <BenchmarksPanel />
    </>
  );
}
