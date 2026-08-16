import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { EvaluationPanel } from "@/components/evaluation/evaluation-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/evaluation");

export default function Page() {
  const { title, description } = routeMeta("/evaluation");

  return (
    <>
      <PageHeader title={title} description={description} />
      {/*
        The panel reads useSearchParams, which is only known at request time.
        Without this boundary the whole route opts out of static rendering.
      */}
      <Suspense fallback={<Skeleton className="h-10 w-full" />}>
        <EvaluationPanel />
      </Suspense>
    </>
  );
}
