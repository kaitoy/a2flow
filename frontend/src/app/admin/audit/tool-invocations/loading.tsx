import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the tool-invocation audit list. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Audit Logs", href: "/admin/audit" }, { label: "Tool Invocations" }]}
      icon={ShieldCheck}
      title="Tool Invocations"
      columns={["Tool", "Server", "Decision", "Denial Reason", "Workflow Execution", "Created At"]}
    />
  );
}
