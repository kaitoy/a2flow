import { ListChecks } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the workflow executions list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflow Executions" }]} />
      <AdminPageHeader title="Workflow Executions" icon={ListChecks} />
      <AdminListSkeleton
        columns={["Workflow", "Agent Skill", "Initiator", "Created At", "Actions"]}
      />
    </AdminPageContainer>
  );
}
