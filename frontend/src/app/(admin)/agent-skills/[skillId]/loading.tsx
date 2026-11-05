"use client";

import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the agent-skill detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.agentSkills"), href: "/agent-skills" }, { label: "…" }]}
      icon={Wand2}
      fields={4}
    />
  );
}
