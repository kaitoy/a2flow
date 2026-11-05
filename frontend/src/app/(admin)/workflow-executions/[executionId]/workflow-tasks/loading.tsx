"use client";

import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the read-only workflow tasks list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflowExecutions"), href: "/workflow-executions" },
        { label: t("workflowExecutions.workflowTasks") },
      ]}
      icon={ListTree}
      title={t("workflowExecutions.workflowTasks")}
      columns={[
        "#",
        t("common.title"),
        t("common.description"),
        t("common.dependsOn"),
        t("common.tools"),
        t("common.status"),
      ]}
    />
  );
}
