import { Tags } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route loading fallback for the new tag form. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Tags", href: "/admin/tags" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Tag" icon={Tags} />
      <FormColumn>
        <FormSkeleton fields={2} />
      </FormColumn>
    </AdminPageContainer>
  );
}
