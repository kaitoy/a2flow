import { FlaskConical } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the new-tool-mock page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Tool Mocks", href: "/admin/mcp-tool-mocks" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Tool Mock" icon={FlaskConical} />
      <FormColumn>
        <FormSkeleton fields={4} />
      </FormColumn>
    </AdminPageContainer>
  );
}
