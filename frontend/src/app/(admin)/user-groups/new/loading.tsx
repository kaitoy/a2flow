"use client";

import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the new user group form. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.userGroups"), href: "/user-groups" }, { label: t("common.new") }]}
      icon={UsersRound}
      title={t("userGroups.newUserGroup")}
      fields={4}
      form="column"
    />
  );
}
