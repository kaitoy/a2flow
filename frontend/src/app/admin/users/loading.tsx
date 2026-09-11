import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the users list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Users" }]}
      icon={UsersIcon}
      title="Users"
      addHref="/admin/users/new"
      addLabel="+ Add user"
      columns={["", "Username", "Name", "Roles", "Enabled", "Created At", "Actions"]}
    />
  );
}
