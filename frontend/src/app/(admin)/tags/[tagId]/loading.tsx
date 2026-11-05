"use client";

import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the tag detail page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.tags"), href: "/tags" }, { label: "…" }]}
      icon={Tags}
      fields={2}
    />
  );
}
