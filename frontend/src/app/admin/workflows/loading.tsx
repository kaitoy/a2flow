import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the workflows list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Workflows" }]}
      icon={WorkflowIcon}
      title="Workflows"
      addHref="/admin/workflows/new"
      addLabel="+ Add workflow"
      columns={["Name", "Prompt", "Agent Skill", "Description", "Created At", "Actions"]}
    />
  );
}
