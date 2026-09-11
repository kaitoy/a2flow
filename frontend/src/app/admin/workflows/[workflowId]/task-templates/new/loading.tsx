import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-template form, matching its field count. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflows", href: "/admin/workflows" },
        { label: "Task Templates" },
        { label: "New" },
      ]}
      icon={ListTree}
      title="New Task Template"
      fields={5}
      form="column"
    />
  );
}
