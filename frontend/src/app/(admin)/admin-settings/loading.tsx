"use client";

import { Settings } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the Admin Settings page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.adminSettings") }]}
      icon={Settings}
      title={t("common.adminSettings")}
      fields={2}
    />
  );
}
