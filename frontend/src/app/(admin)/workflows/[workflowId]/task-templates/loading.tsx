"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/**
 * Route loading fallback for the task templates list page. `loading.tsx`
 * receives no `params` prop, so the `workflowId` needed for the breadcrumb and
 * "add" link is read via `useParams`, matching the real page.
 */
export default function Loading() {
  const t = useT();
  const { workflowId } = useParams<{ workflowId: string }>();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflows"), href: "/workflows" },
        { label: "…", href: `/workflows/${workflowId}` },
        { label: t("workflows.taskTemplates") },
      ]}
      icon={ListTree}
      title={t("workflows.taskTemplates")}
      addHref={`/workflows/${workflowId}/task-templates/new`}
      addLabel={t("workflows.addTask")}
      columns={[
        "#",
        t("common.title"),
        t("common.description"),
        t("common.dependsOn"),
        t("common.tools"),
        t("common.actions"),
      ]}
    />
  );
}
