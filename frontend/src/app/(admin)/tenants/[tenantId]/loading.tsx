"use client";

import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the tenant detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tenants"), href: "/tenants" }, { label: "…" }]}
      icon={Building2}
      fields={3}
    />
  );
}
