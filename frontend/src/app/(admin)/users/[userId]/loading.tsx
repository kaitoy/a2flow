"use client";

import { User as UsersIcon } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the user detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.users"), href: "/users" }, { label: "…" }]}
      icon={UsersIcon}
      fields={6}
    />
  );
}
