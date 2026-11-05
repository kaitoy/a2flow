"use client";

import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-tool-mock page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.toolMocks"), href: "/mcp-tool-mocks" },
        { label: t("common.new") },
      ]}
      icon={FlaskConical}
      title={t("mcpToolMocks.newToolMock")}
      fields={4}
      form="column"
    />
  );
}
