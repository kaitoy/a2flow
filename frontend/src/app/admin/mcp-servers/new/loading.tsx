import { Server } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the new-MCP-server page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "MCP Servers", href: "/admin/mcp-servers" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New MCP Server" icon={Server} />
      <FormColumn>
        <FormSkeleton fields={3} />
      </FormColumn>
    </AdminPageContainer>
  );
}
