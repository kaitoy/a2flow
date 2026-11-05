"use client";

import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the knowledge base detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.knowledgeBases"), href: "/knowledge-bases" }, { label: "…" }]}
      icon={BookOpen}
      fields={2}
    />
  );
}
