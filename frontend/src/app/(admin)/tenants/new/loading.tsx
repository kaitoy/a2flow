"use client";

import { Building2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-tenant page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tenants"), href: "/tenants" }, { label: t("common.new") }]}
      icon={Building2}
      title={t("tenants.newTenant")}
      fields={3}
      form="column"
    />
  );
}
