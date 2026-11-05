"use client";

import { CheckCircle2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";
import { useT } from "@/i18n/provider";

/** Route-transition fallback for the approval detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  const t = useT();
  return (
    <AdminLoading
      crumbs={[{ label: t("common.approvals"), href: "/approvals" }, { label: "…" }]}
      icon={CheckCircle2}
      fields={5}
    />
  );
}
