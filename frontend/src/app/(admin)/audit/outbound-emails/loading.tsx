"use client";

import { Mail } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the outbound-email audit list. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.auditLogs"), href: "/audit" }, { label: t("common.emails") }]}
      icon={Mail}
      title={t("audit.outboundEmails")}
      columns={[
        t("audit.to"),
        t("audit.subject"),
        t("common.status"),
        t("audit.attempts"),
        t("audit.sentAt"),
        t("audit.lastError"),
      ]}
    />
  );
}
