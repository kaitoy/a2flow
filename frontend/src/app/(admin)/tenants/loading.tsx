"use client";

import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the tenants list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tenants") }]}
      icon={Building2}
      title={t("common.tenants")}
      addHref="/tenants/new"
      addLabel={t("tenants.addTenant")}
      columns={[
        t("tenants.displayName"),
        t("common.name"),
        t("common.enabled"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
