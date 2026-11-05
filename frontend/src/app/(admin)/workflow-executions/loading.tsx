"use client";

import { ListChecks } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the workflow executions list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.workflowExecutions") }]}
      icon={ListChecks}
      title={t("common.workflowExecutions")}
      columns={[
        t("workflowExecutions.workflow"),
        t("common.agentSkill"),
        t("workflowExecutions.initiator"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
