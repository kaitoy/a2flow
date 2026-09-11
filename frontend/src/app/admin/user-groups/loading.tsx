import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the user groups list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "User Groups" }]}
      icon={UsersRound}
      title="User Groups"
      addHref="/admin/user-groups/new"
      addLabel="+ Add group"
      columns={["Name", "Description", "Roles", "Members", "Created At", "Actions"]}
    />
  );
}
