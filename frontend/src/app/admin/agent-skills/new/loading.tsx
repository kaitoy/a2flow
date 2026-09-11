import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-agent-skill page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Agent Skills", href: "/admin/agent-skills" }, { label: "New" }]}
      icon={Wand2}
      title="New Agent Skill"
      fields={4}
      form="column"
    />
  );
}
