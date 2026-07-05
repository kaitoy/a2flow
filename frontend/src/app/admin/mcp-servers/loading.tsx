import { Server } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the MCP servers list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "MCP Servers" }]} />
      <AdminPageHeader
        title="MCP Servers"
        icon={Server}
        addHref="/admin/mcp-servers/new"
        addLabel="+ Add server"
      />
      <AdminListSkeleton columns={["Name", "URL", "Headers", "Created At", "Actions"]} />
    </AdminPageContainer>
  );
}
