"use client";

import { KeyRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the new-secret page. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.secrets"), href: "/secrets" }, { label: t("common.new") }]}
      icon={KeyRound}
      title={t("secrets.newSecret")}
      fields={3}
      form="column"
    />
  );
}
