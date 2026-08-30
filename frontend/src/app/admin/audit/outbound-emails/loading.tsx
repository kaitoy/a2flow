import { Mail } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the outbound-email audit list. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Emails" },
        ]}
      />
      <AdminPageHeader title="Outbound Emails" icon={Mail} />
      <AdminListSkeleton
        columns={["To", "Subject", "Status", "Attempts", "Sent At", "Last Error"]}
      />
    </AdminPageContainer>
  );
}
