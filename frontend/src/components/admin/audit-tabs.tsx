/**
 * @module audit-tabs — the tab bar shared by the four `/admin/audit` lists.
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
import { SegmentedControl } from "@/components/ui/segmented-control";

/** The audit lists, in the order their tabs appear. */
export const AUDIT_TABS = [
  { value: "tool-invocations", label: "Tool Invocations" },
  { value: "impersonations", label: "Impersonations" },
  { value: "approval-certificates", label: "Certificates" },
  { value: "outbound-emails", label: "Emails" },
] as const;

/** The route segment identifying one audit list. */
export type AuditTab = (typeof AUDIT_TABS)[number]["value"];

/** Props for {@link AuditTabs}. */
export interface AuditTabsProps {
  /** The list currently being shown. */
  active: AuditTab;
}

/**
 * The audit section's tab bar. Selecting a tab navigates to that list.
 *
 * @param props - The currently active list.
 */
export function AuditTabs({ active }: AuditTabsProps) {
  const router = useRouter();
  return (
    <SegmentedControl
      options={AUDIT_TABS}
      value={active}
      onChange={(tab) => router.push(`/admin/audit/${tab}`)}
      aria-label="Audit log"
      className="mb-4"
    />
  );
}
