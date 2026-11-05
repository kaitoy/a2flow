"use client";

import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the tags list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tags") }]}
      icon={Tags}
      title={t("common.tags")}
      addHref="/tags/new"
      addLabel={t("tags.addTag")}
      columns={[t("common.name"), t("tags.preview"), t("common.createdAt"), t("common.actions")]}
    />
  );
}
