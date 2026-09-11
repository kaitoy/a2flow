import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the user group detail page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "User Groups", href: "/admin/user-groups" }, { label: "…" }]}
      icon={UsersRound}
      fields={4}
    />
  );
}
