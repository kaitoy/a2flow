import { VenetianMask } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the impersonation audit list. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Impersonations" },
        ]}
      />
      <AdminPageHeader title="Impersonations" icon={VenetianMask} />
      <AdminListSkeleton
        columns={["Impersonator", "Target User", "State", "Started At", "Ended At", "Actions"]}
      />
    </AdminPageContainer>
  );
}
