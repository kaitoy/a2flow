"use client";

import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-MCP-server page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.mcpServers"), href: "/mcp-servers" }, { label: t("common.new") }]}
      icon={Server}
      title={t("mcpServers.newMcpServer")}
      fields={3}
      form="column"
    />
  );
}
