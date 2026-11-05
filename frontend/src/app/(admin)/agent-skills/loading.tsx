"use client";

import { Wand2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the agent skills list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.agentSkills") }]}
      icon={Wand2}
      title={t("common.agentSkills")}
      addHref="/agent-skills/new"
      addLabel={t("agentSkills.addSkill")}
      columns={[
        t("common.name"),
        t("common.repoUrl"),
        t("common.repoPath"),
        t("common.status"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
