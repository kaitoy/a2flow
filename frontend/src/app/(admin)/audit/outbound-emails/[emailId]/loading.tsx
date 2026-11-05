"use client";

import { Mail } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the outbound-email detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.auditLogs"), href: "/audit" },
        { label: t("common.emails"), href: "/audit/outbound-emails" },
        { label: "…" },
      ]}
      icon={Mail}
      fields={7}
    />
  );
}
