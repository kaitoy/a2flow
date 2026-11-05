"use client";

import { ShieldCheck } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the tenant settings page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tenantSettings") }]}
      icon={ShieldCheck}
      title={t("common.tenantSettings")}
      fields={2}
    />
  );
}
