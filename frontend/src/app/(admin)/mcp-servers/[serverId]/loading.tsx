"use client";

import { Server } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the MCP-server detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.mcpServers"), href: "/mcp-servers" }, { label: "…" }]}
      icon={Server}
      fields={3}
    />
  );
}
