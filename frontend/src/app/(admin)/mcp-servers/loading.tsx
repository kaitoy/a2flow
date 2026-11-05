"use client";

import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the MCP servers list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.mcpServers") }]}
      icon={Server}
      title={t("common.mcpServers")}
      addHref="/mcp-servers/new"
      addLabel={t("mcpServers.addServer")}
      columns={[t("common.name"), t("common.endpoint"), t("common.createdAt"), t("common.actions")]}
    />
  );
}
