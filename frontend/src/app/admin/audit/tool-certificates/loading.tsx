import { BadgeCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the approval-certificate audit list. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Audit Logs", href: "/admin/audit" }, { label: "Certificates" }]}
      icon={BadgeCheck}
      title="Approval Certificates"
      columns={["Serial", "Approval", "State", "Allowed Tools", "Not After", "Revoked At"]}
    />
  );
}
