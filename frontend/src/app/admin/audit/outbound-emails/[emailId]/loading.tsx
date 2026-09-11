import { Mail } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the outbound-email detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Audit Logs", href: "/admin/audit" },
        { label: "Emails", href: "/admin/audit/outbound-emails" },
        { label: "…" },
      ]}
      icon={Mail}
      fields={7}
    />
  );
}
