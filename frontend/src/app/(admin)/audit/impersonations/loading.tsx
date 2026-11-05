"use client";

import { VenetianMask } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the impersonation audit list. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.impersonations") },
      ]}
      icon={VenetianMask}
      title={t("common.impersonations")}
      columns={[
        t("audit.impersonator"),
        t("audit.targetUser"),
        t("audit.state"),
        t("audit.startedAt"),
        t("audit.endedAt"),
        t("common.actions"),
      ]}
    />
  );
}
