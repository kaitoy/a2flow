import { BadgeCheck } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the approval-certificate audit list. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Certificates" },
        ]}
      />
      <AdminPageHeader title="Approval Certificates" icon={BadgeCheck} />
      <AdminListSkeleton
        columns={["Serial", "Approval", "State", "Allowed Tools", "Not After", "Revoked At"]}
      />
    </AdminPageContainer>
  );
}
