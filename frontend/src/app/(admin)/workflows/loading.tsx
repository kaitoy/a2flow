"use client";

import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the workflows list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.workflows") }]}
      icon={WorkflowIcon}
      title={t("common.workflows")}
      addHref="/workflows/new"
      addLabel={t("workflows.addWorkflow")}
      columns={[
        t("common.name"),
        t("common.prompt"),
        t("common.agentSkill"),
        t("common.description"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
