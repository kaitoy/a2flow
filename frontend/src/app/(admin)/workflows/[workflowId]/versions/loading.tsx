"use client";

import { History } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/**
 * Route loading fallback for the version history page. `loading.tsx` receives
 * no `params` prop, so the `workflowId` for the breadcrumb is read via
 * `useParams`, matching the real page.
 */
export default function Loading() {
  const t = useT();
  const { workflowId } = useParams<{ workflowId: string }>();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflows"), href: "/workflows" },
        { label: "…", href: `/workflows/${workflowId}` },
        { label: t("workflows.versions") },
      ]}
      icon={History}
      title={t("workflows.versionHistory2")}
      columns={[
        t("common.version"),
        t("common.name"),
        t("common.description"),
        t("common.actions"),
      ]}
    />
  );
}
