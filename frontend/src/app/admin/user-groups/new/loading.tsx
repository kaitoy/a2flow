import { UsersRound } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route loading fallback for the new user group form. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "User Groups", href: "/admin/user-groups" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New User Group" icon={UsersRound} />
      <FormColumn>
        <FormSkeleton fields={4} />
      </FormColumn>
    </AdminPageContainer>
  );
}
