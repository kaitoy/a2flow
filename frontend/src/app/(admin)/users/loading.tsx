"use client";

import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the users list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.users") }]}
      icon={UsersIcon}
      title={t("common.users")}
      addHref="/users/new"
      addLabel={t("users.addUser")}
      columns={[
        "",
        t("common.username"),
        t("common.name"),
        t("common.roles"),
        t("common.enabled"),
        t("common.createdAt"),
        t("common.actions"),
      ]}
    />
  );
}
