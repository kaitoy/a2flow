import { VenetianMask } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the impersonation-session detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Audit Logs", href: "/audit" },
        { label: "Impersonations", href: "/audit/impersonations" },
        { label: "…" },
      ]}
      icon={VenetianMask}
      fields={5}
    />
  );
}
