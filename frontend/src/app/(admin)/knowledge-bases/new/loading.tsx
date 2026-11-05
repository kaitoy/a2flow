"use client";

import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-knowledge-base page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.knowledgeBases"), href: "/knowledge-bases" },
        { label: t("common.new") },
      ]}
      icon={BookOpen}
      title={t("knowledgeBases.newKnowledgeBase")}
      fields={2}
      form="column"
    />
  );
}
