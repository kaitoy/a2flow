"use client";

import { BadgeCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the approval-certificate audit list. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.certificates") },
      ]}
      icon={BadgeCheck}
      title={t("audit.approvalCertificates")}
      columns={[
        t("audit.serial"),
        t("common.approval"),
        t("audit.state"),
        t("audit.allowedTools"),
        t("audit.notAfter"),
        t("audit.revokedAt"),
      ]}
    />
  );
}
