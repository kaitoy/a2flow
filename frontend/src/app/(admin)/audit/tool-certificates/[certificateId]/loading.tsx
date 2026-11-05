"use client";

import { BadgeCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the approval-certificate detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.certificates"), href: "/audit/tool-certificates" },
        { label: "…" },
      ]}
      icon={BadgeCheck}
      fields={7}
    />
  );
}
