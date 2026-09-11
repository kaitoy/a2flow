import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the new user group form. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "User Groups", href: "/admin/user-groups" }, { label: "New" }]}
      icon={UsersRound}
      title="New User Group"
      fields={4}
      form="column"
    />
  );
}
