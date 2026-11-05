"use client";

import { ListTree } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-template form, matching its field count. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.workflows"), href: "/workflows" },
        { label: t("workflows.taskTemplates") },
        { label: t("common.new") },
      ]}
      icon={ListTree}
      title={t("workflows.newTaskTemplate")}
      fields={5}
      form="column"
    />
  );
}
