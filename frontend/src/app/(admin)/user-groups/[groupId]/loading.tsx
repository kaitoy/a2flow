"use client";

import { UsersRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the user group detail page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.userGroups"), href: "/user-groups" }, { label: "…" }]}
      icon={UsersRound}
      fields={4}
    />
  );
}
