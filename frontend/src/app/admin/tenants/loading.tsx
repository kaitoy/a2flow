import { Building2 } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the tenants list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tenants" }]} />
      <AdminPageHeader
        title="Tenants"
        icon={Building2}
        addHref="/admin/tenants/new"
        addLabel="+ Add tenant"
      />
      <AdminListSkeleton columns={["Display Name", "Name", "Enabled", "Actions"]} />
    </AdminPageContainer>
  );
}
