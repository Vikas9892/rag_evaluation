import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { QueryPanel } from "@/components/query/query-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/query");

export default function QueryPage() {
  const { title, description } = routeMeta("/query");

  return (
    <>
      <PageHeader title={title} description={description} />
      {/*
        QueryPanel reads useSearchParams, which is only known at request time.
        Without this boundary the whole route opts out of static rendering —
        Next fails the build rather than doing it silently.
      */}
      <Suspense fallback={<Skeleton className="h-10 w-full" />}>
        <QueryPanel />
      </Suspense>
    </>
  );
}
