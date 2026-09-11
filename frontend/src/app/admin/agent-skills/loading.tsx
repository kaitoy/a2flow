import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the agent skills list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Agent Skills" }]}
      icon={Wand2}
      title="Agent Skills"
      addHref="/admin/agent-skills/new"
      addLabel="+ Add skill"
      columns={["Name", "Repo URL", "Repo Path", "Status", "Created At", "Actions"]}
    />
  );
}
