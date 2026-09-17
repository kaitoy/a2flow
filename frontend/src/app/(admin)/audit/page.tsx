/**
 * @module AuditIndexPage — Redirects the bare /audit route to the first
 * audit list. The sidebar links here rather than to a specific list so its
 * active-state highlight (a `startsWith` match) covers all four tabs.
 */
import { redirect } from "next/navigation";

export default function AuditIndexPage() {
  redirect("/audit/tool-invocations");
}
