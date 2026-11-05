"use client";

import { Settings2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the system settings page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.systemSettings") }]}
      icon={Settings2}
      title={t("common.systemSettings")}
      fields={8}
    />
  );
}
