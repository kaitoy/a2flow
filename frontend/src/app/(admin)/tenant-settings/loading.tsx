import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the tenant settings page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tenant Settings" }]}
      icon={ShieldCheck}
      title="Tenant Settings"
      fields={2}
    />
  );
}
