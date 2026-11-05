"use client";

import { ListChecks } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the workflow execution detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflowExecutions"), href: "/workflow-executions" },
        { label: "…" },
      ]}
      icon={ListChecks}
      fields={6}
    />
  );
}
