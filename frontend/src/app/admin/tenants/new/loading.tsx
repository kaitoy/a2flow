import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-tenant page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tenants", href: "/admin/tenants" }, { label: "New" }]}
      icon={Building2}
      title="New Tenant"
      fields={3}
      form="column"
    />
  );
}
