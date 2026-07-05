import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the new-workflow page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Workflow" icon={WorkflowIcon} />
      <FormColumn>
        <FormSkeleton fields={4} />
      </FormColumn>
    </AdminPageContainer>
  );
}
