"use client";

import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the task-template detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflows"), href: "/workflows" },
        { label: t("workflows.taskTemplates") },
        { label: "…" },
      ]}
      icon={ListTree}
      fields={5}
    />
  );
}
