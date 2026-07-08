import { KeyRound } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the secrets list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Secrets" }]} />
      <AdminPageHeader
        title="Secrets"
        icon={KeyRound}
        addHref="/admin/secrets/new"
        addLabel="+ Add secret"
      />
      <AdminListSkeleton columns={["Name", "Type", "Reference", "Created At", "Actions"]} />
    </AdminPageContainer>
  );
}
