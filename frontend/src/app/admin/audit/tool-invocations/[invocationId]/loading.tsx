import { ShieldCheck } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the tool-invocation detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Tool Invocations", href: "/admin/audit/tool-invocations" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={ShieldCheck} />}>
        <FormSkeleton fields={8} />
      </FormLayout>
    </AdminPageContainer>
  );
}
