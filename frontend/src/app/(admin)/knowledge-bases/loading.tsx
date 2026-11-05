"use client";

import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the knowledge bases list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.knowledgeBases") }]}
      icon={BookOpen}
      title={t("common.knowledgeBases")}
      addHref="/knowledge-bases/new"
      addLabel={t("knowledgeBases.addKnowledgeBase")}
      columns={[t("common.name"), t("common.description"), t("common.actions")]}
    />
  );
}
