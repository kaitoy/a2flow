import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the workflows list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflows" }]} />
      <AdminPageHeader
        title="Workflows"
        icon={WorkflowIcon}
        addHref="/admin/workflows/new"
        addLabel="+ Add workflow"
      />
      <AdminListSkeleton
        columns={["Name", "Prompt", "Agent Skill", "Description", "Created At", "Actions"]}
      />
    </AdminPageContainer>
  );
}
