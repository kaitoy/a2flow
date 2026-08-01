import { KeyRound } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the edit-secret page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Secrets", href: "/admin/secrets" },
          { label: "Edit" },
        ]}
      />
      <FormLayout header={<AdminPageHeader title="Edit Secret" icon={KeyRound} />}>
        <FormSkeleton fields={3} />
      </FormLayout>
    </AdminPageContainer>
  );
}
