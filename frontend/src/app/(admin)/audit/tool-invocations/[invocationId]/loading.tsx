"use client";

import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the tool-invocation detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.toolInvocations"), href: "/audit/tool-invocations" },
        { label: "…" },
      ]}
      icon={ShieldCheck}
      fields={8}
    />
  );
}
