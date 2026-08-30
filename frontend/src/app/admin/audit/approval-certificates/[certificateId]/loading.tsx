import { BadgeCheck } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the approval-certificate detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Certificates", href: "/admin/audit/approval-certificates" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={BadgeCheck} />}>
        <FormSkeleton fields={7} />
      </FormLayout>
    </AdminPageContainer>
  );
}
