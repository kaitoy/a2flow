import { UsersRound } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the user groups list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "User Groups" }]} />
      <AdminPageHeader
        title="User Groups"
        icon={UsersRound}
        addHref="/admin/user-groups/new"
        addLabel="+ Add group"
      />
      <AdminListSkeleton
        columns={["Name", "Description", "Roles", "Members", "Created At", "Actions"]}
      />
    </AdminPageContainer>
  );
}
