import { UsersRound } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route loading fallback for the user group detail page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "User Groups", href: "/admin/user-groups" },
          { label: "…" },
        ]}
      />
      <FormLayout header={<AdminPageHeader icon={UsersRound} />}>
        <FormSkeleton fields={4} />
      </FormLayout>
    </AdminPageContainer>
  );
}
