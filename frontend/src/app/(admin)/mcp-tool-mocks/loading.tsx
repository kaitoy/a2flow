"use client";

import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the tool mocks list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.toolMocks") }]}
      icon={FlaskConical}
      title={t("common.toolMocks")}
      addHref="/mcp-tool-mocks/new"
      addLabel={t("mcpToolMocks.addToolMock")}
      columns={[
        t("common.name"),
        t("common.tool"),
        t("common.server"),
        t("common.description"),
        t("common.actions"),
      ]}
    />
  );
}
