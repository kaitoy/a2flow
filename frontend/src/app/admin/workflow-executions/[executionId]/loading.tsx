import { ListChecks } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the workflow execution detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflow Executions", href: "/admin/workflow-executions" },
        { label: "…" },
      ]}
      icon={ListChecks}
      fields={6}
    />
  );
}
