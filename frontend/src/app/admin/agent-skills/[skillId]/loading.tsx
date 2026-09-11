import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the agent-skill detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Agent Skills", href: "/admin/agent-skills" }, { label: "…" }]}
      icon={Wand2}
      fields={4}
    />
  );
}
