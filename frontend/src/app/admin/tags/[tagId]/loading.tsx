import { Tags } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route loading fallback for the tag detail page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Tags", href: "/admin/tags" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={Tags} />}>
        <FormSkeleton fields={2} />
      </FormLayout>
    </AdminPageContainer>
  );
}
