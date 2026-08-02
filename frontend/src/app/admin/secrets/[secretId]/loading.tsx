import { KeyRound } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the secret detail page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Secrets", href: "/admin/secrets" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={KeyRound} />}>
        <FormSkeleton fields={3} />
      </FormLayout>
    </AdminPageContainer>
  );
}
