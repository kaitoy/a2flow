import { Wand2 } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the agent skills list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Agent Skills" }]} />
      <AdminPageHeader
        title="Agent Skills"
        icon={Wand2}
        addHref="/admin/agent-skills/new"
        addLabel="+ Add skill"
      />
      <AdminListSkeleton
        columns={["Name", "Repo URL", "Repo Path", "Description", "Created At", "Actions"]}
      />
    </AdminPageContainer>
  );
}
