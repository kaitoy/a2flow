import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the tool-invocation detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Audit Logs", href: "/audit" },
        { label: "Tool Invocations", href: "/audit/tool-invocations" },
        { label: "…" },
      ]}
      icon={ShieldCheck}
      fields={8}
    />
  );
}
