import { CheckCircle2 } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the approval detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Approvals", href: "/admin/approvals" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={CheckCircle2} />}>
        <FormSkeleton fields={5} />
      </FormLayout>
    </AdminPageContainer>
  );
}
