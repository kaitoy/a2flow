import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the user detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Users", href: "/admin/users" }, { label: "…" }]}
      icon={UsersIcon}
      fields={6}
    />
  );
}
