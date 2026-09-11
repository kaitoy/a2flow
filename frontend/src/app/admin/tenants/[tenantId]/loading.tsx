import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the tenant detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tenants", href: "/admin/tenants" }, { label: "…" }]}
      icon={Building2}
      fields={3}
    />
  );
}
