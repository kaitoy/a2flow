import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the edit-workflow page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "Edit" },
        ]}
      />
      <AdminPageHeader title="Edit Workflow" icon={WorkflowIcon} />
      <FormColumn>
        <FormSkeleton fields={4} />
      </FormColumn>
    </AdminPageContainer>
  );
}
