/**
 * @module audit-tabs — the tab bar shared by the four `/audit` lists.
 *
 * The audit section is one sidebar entry rather than four, so the switch between
 * its lists lives here instead. Every list page renders this directly under its
 * breadcrumbs, which is what keeps the four from drifting apart — the labels and
 * the route each tab points at are defined once.
 *
 * Built on {@link SegmentedControl}, so the tabs are a real `tablist`: arrow
 * keys, Home, and End move the selection.
 */
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useT } from "@/i18n/provider";

/** The audit lists, in the order their tabs appear. */
export const AUDIT_TABS = [
  { value: "tool-invocations", label: "common.toolInvocations" },
  { value: "impersonations", label: "common.impersonations" },
  { value: "tool-certificates", label: "common.certificates" },
  { value: "outbound-emails", label: "common.emails" },
] as const;

/** The route segment identifying one audit list. */
export type AuditTab = (typeof AUDIT_TABS)[number]["value"];

/**
 * The tab a click just left. Each list renders its own bar, so a switch remounts
 * it; the new bar starts its pill here so the switch still reads as a slide. Set
 * only by a click, so arriving any other way (the sidebar, back/forward) places
 * the pill without moving it.
 */
let leftTab: AuditTab | null = null;

/** Props for {@link AuditTabs}. */
export interface AuditTabsProps {
  /** The list currently being shown. */
  active: AuditTab;
}

/**
 * The audit section's tab bar. Selecting a tab navigates to that list, and the
 * next list's bar slides its pill over from the tab just left (see {@link leftTab}).
 *
 * @param props - The currently active list.
 */
export function AuditTabs({ active }: AuditTabsProps) {
  const t = useT();
  const router = useRouter();
  // Read once on mount and consumed, so only the bar right after the click slides.
  const [slideFrom] = useState(() => leftTab);
  useEffect(() => {
    leftTab = null;
  }, []);
  return (
    <SegmentedControl
      options={AUDIT_TABS}
      value={active}
      slideFrom={slideFrom ?? undefined}
      onChange={(tab) => {
        leftTab = active;
        router.push(`/audit/${tab}`);
      }}
      aria-label={t("admin.auditLog")}
      className="mb-4"
    />
  );
}
