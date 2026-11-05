"use client";

import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the user groups list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.userGroups") }]}
      icon={UsersRound}
      title={t("common.userGroups")}
      addHref="/user-groups/new"
      addLabel={t("userGroups.addGroup")}
      columns={[
        t("common.name"),
        t("common.description"),
        t("common.roles"),
        t("common.members"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
