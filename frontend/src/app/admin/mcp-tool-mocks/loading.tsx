import { FlaskConical } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the tool mocks list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tool Mocks" }]} />
      <AdminPageHeader
        title="Tool Mocks"
        icon={FlaskConical}
        addHref="/admin/mcp-tool-mocks/new"
        addLabel="+ Add tool mock"
      />
      <AdminListSkeleton columns={["Name", "Tool", "Server", "Description", "Actions"]} />
    </AdminPageContainer>
  );
}
