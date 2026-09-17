import { ListChecks } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the workflow executions list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Workflow Executions" }]}
      icon={ListChecks}
      title="Workflow Executions"
      columns={["Workflow", "Agent Skill", "Initiator", "Created At", "Actions"]}
    />
  );
}
