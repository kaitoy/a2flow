"use client";

import { VenetianMask } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the impersonation-session detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.impersonations"), href: "/audit/impersonations" },
        { label: "…" },
      ]}
      icon={VenetianMask}
      fields={5}
    />
  );
}
