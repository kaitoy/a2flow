import { ListChecks } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the workflow execution detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Executions", href: "/admin/workflow-executions" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={ListChecks} />}>
        <FormSkeleton fields={6} />
      </FormLayout>
    </AdminPageContainer>
  );
}
