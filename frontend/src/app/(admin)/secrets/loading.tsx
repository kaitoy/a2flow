"use client";

import { KeyRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the secrets list page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.secrets") }]}
      icon={KeyRound}
      title={t("common.secrets")}
      addHref="/secrets/new"
      addLabel={t("secrets.addSecret")}
      columns={[t("common.name"), t("common.type"), t("common.createdAt"), t("common.actions")]}
    />
  );
}
