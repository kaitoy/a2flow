"use client";

import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the new tag form. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tags"), href: "/tags" }, { label: t("common.new") }]}
      icon={Tags}
      title={t("tags.newTag")}
      fields={2}
      form="column"
    />
  );
}
