"use client";

import { ConsoleFrame } from "@/components/dashboard/console-panel";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { useDashboardLook } from "@/hooks/useDashboardLook";
import { useT } from "@/i18n/provider";

/** Route loading fallback for the operations dashboard, in the viewer's chosen look. */
export default function Loading() {
  const t = useT();
  const [look] = useDashboardLook();
  return (
    <ConsoleFrame look={look}>
      <h1 className="font-display text-3xl font-semibold tracking-tight text-on-surface">
        {t("common.dashboard")}
      </h1>
      <DashboardSkeleton />
    </ConsoleFrame>
  );
}
