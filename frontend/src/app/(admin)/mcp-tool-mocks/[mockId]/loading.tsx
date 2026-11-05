"use client";

import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the tool-mock detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.toolMocks"), href: "/mcp-tool-mocks" }, { label: "…" }]}
      icon={FlaskConical}
      fields={4}
    />
  );
}
