"use client";

import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-user page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.users"), href: "/users" }, { label: t("common.new") }]}
      icon={UsersIcon}
      title={t("users.newUser")}
      fields={5}
      form="column"
    />
  );
}
