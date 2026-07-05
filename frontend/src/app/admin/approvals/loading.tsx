import { CheckCircle2 } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the approvals list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Approvals" }]} />
      <AdminPageHeader title="Approvals" icon={CheckCircle2} />
      <AdminListSkeleton
        columns={["Title", "Status", "Approver", "Comment", "Session", "Created At"]}
      />
    </AdminPageContainer>
  );
}
