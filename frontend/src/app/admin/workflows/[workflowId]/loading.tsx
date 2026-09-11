import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the workflow detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Workflows", href: "/admin/workflows" }, { label: "…" }]}
      icon={WorkflowIcon}
      fields={4}
    />
  );
}
