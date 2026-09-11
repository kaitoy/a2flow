import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the MCP servers list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "MCP Servers" }]}
      icon={Server}
      title="MCP Servers"
      addHref="/admin/mcp-servers/new"
      addLabel="+ Add server"
      columns={["Name", "Endpoint", "Created At", "Actions"]}
    />
  );
}
