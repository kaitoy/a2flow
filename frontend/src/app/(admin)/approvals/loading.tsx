"use client";

import { CheckCircle2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the approvals list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.approvals") }]}
      icon={CheckCircle2}
      title={t("common.approvals")}
      columns={[
        t("common.title"),
        t("common.status"),
        t("approvals.approver"),
        t("approvals.decidedBy"),
        t("common.comment"),
        t("common.session"),
        t("common.createdAt"),
        t("common.description"),
        t("approvals.decidedAt"),
      ]}
    />
  );
}
