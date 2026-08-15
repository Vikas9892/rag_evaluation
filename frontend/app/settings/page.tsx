import { PageHeader } from "@/components/layout/page-header";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { metadataFor, routeMeta } from "@/lib/page-meta";

export const metadata = metadataFor("/settings");

export default function Page() {
  const { title, description } = routeMeta("/settings");

  return (
    <>
      <PageHeader title={title} description={description} />
      <SettingsPanel />
    </>
  );
}
