import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-MCP-server page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "MCP Servers", href: "/admin/mcp-servers" }, { label: "New" }]}
      icon={Server}
      title="New MCP Server"
      fields={3}
      form="column"
    />
  );
}
