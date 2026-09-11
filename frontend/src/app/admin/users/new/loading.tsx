import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-user page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Users", href: "/admin/users" }, { label: "New" }]}
      icon={UsersIcon}
      title="New User"
      fields={5}
      form="column"
    />
  );
}
