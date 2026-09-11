import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the tenants list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tenants" }]}
      icon={Building2}
      title="Tenants"
      addHref="/admin/tenants/new"
      addLabel="+ Add tenant"
      columns={["Display Name", "Name", "Enabled", "Created At", "Actions"]}
    />
  );
}
