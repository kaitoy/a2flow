import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the read-only workflow tasks list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflow Executions", href: "/admin/workflow-executions" },
        { label: "Workflow Tasks" },
      ]}
      icon={ListTree}
      title="Workflow Tasks"
      columns={["#", "Title", "Description", "Depends on", "Tools", "Status"]}
    />
  );
}
