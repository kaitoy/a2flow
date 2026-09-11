import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the task-template detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflows", href: "/admin/workflows" },
        { label: "Task Templates" },
        { label: "…" },
      ]}
      icon={ListTree}
      fields={5}
    />
  );
}
