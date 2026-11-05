"use client";

import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the tool-invocation audit list. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.toolInvocations") },
      ]}
      icon={ShieldCheck}
      title={t("common.toolInvocations")}
      columns={[
        t("common.tool"),
        t("common.server"),
        t("common.decision"),
        t("common.denialReason"),
        t("common.workflowExecution"),
        t("common.createdAt"),
      ]}
    />
  );
}
