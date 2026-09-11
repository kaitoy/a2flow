import { Mail } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the outbound-email audit list. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Audit Logs", href: "/admin/audit" }, { label: "Emails" }]}
      icon={Mail}
      title="Outbound Emails"
      columns={["To", "Subject", "Status", "Attempts", "Sent At", "Last Error"]}
    />
  );
}
