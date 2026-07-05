import { Users as UsersIcon } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the users list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Users" }]} />
      <AdminPageHeader
        title="Users"
        icon={UsersIcon}
        addHref="/admin/users/new"
        addLabel="+ Add user"
      />
      <AdminListSkeleton
        columns={["", "Username", "Name", "Email", "Enabled", "Verified", "Actions"]}
      />
    </AdminPageContainer>
  );
}
