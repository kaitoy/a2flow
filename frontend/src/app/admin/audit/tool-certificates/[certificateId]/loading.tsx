import { BadgeCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the approval-certificate detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Audit Logs", href: "/admin/audit" },
        { label: "Certificates", href: "/admin/audit/tool-certificates" },
        { label: "…" },
      ]}
      icon={BadgeCheck}
      fields={7}
    />
  );
}
