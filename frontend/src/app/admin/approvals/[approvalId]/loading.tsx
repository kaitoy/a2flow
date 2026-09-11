import { CheckCircle2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the approval detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Approvals", href: "/admin/approvals" }, { label: "…" }]}
      icon={CheckCircle2}
      fields={5}
    />
  );
}
