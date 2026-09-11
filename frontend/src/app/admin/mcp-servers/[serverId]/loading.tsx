import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the MCP-server detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "MCP Servers", href: "/admin/mcp-servers" }, { label: "…" }]}
      icon={Server}
      fields={3}
    />
  );
}
