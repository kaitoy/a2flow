"use client";

import { Workflow as WorkflowIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the workflow detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.workflows"), href: "/workflows" }, { label: "…" }]}
      icon={WorkflowIcon}
      fields={4}
    />
  );
}
