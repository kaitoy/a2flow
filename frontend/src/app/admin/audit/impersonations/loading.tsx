import { VenetianMask } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the impersonation audit list. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Audit Logs", href: "/admin/audit" }, { label: "Impersonations" }]}
      icon={VenetianMask}
      title="Impersonations"
      columns={["Impersonator", "Target User", "State", "Started At", "Ended At", "Actions"]}
    />
  );
}
