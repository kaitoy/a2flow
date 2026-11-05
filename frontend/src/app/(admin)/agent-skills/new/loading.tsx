"use client";

import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-agent-skill page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[
        { label: t("common.agentSkills"), href: "/agent-skills" },
        { label: t("common.new") },
      ]}
      icon={Wand2}
      title={t("agentSkills.newAgentSkill")}
      fields={4}
      form="column"
    />
  );
}
