import { VenetianMask } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the impersonation-session detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Audit Logs", href: "/admin/audit" },
        { label: "Impersonations", href: "/admin/audit/impersonations" },
        { label: "…" },
      ]}
      icon={VenetianMask}
      fields={5}
    />
  );
}
