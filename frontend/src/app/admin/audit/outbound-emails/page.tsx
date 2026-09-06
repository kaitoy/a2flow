/** @module AuditOutboundEmailsPage — Audit list of the outgoing notification-email queue. */
"use client";

import { Mail } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { AuditTabs } from "@/components/admin/audit-tabs";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { Badge } from "@/components/ui/badge";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { listOutboundEmails, type OutboundEmail } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Page size for the audit list. */
const LIMIT = 50;

/** Filter options for a queued message's delivery status. */
const STATUS_OPTIONS = [
  { label: "Pending", value: "pending" },
  { label: "Sending", value: "sending" },
  { label: "Sent", value: "sent" },
  { label: "Failed", value: "failed" },
];

/**
 * Audit list of the messages A2Flow has queued for delivery.
 *
 * A row is one notification email, rendered when the notification was produced
 * and then drained by the mail worker. `failed` rows are kept as dead letters
 * rather than removed, so a delivery that never landed stays visible with the
 * reason recorded against it.
 *
 * The body is available through the column picker and in full on a row's detail
 * page — it is what makes this a read of message content, which is why the list
 * is admin-only rather than open to any signed-in viewer.
 */
export default function AuditOutboundEmailsPage() {
  const {
    rows,
    loading,
    refreshing,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload,
  } = useTableQuery<OutboundEmail>(listOutboundEmails, { limit: LIMIT });

  const names = useUserNames(rows.flatMap((e) => [e.createdBy, e.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((e) => e.tenantId) : []);

  const columns = useMemo<ColumnDef<OutboundEmail>[]>(
    () => [
      ...(isAllTenantsView ? [tenantColumn<OutboundEmail>(tenantNames)] : []),
      idColumn<OutboundEmail>(),
      {
        header: "To",
        sortField: "toEmail",
        filterField: "toEmail",
        visibility: "always",
        cell: (e) => (
          <Link
            href={`/admin/audit/outbound-emails/${e.id}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {e.toEmail}
          </Link>
        ),
      },
      {
        header: "Subject",
        sortField: "subject",
        filterField: "subject",
        cell: (e) => e.subject,
      },
      {
        header: "Status",
        noTruncate: true,
        sortField: "status",
        filterField: "status",
        filterOp: "eq",
        filterOptions: STATUS_OPTIONS,
        cell: (e) => <Badge>{e.status}</Badge>,
      },
      {
        header: "Attempts",
        sortField: "attempts",
        cell: (e) => e.attempts,
      },
      {
        header: "Sent At",
        sortField: "sentAt",
        cell: (e) =>
          e.sentAt ? (
            <DateTime value={e.sentAt} className="text-on-surface-variant" />
          ) : (
            EMPTY_VALUE
          ),
      },
      {
        header: "Last Error",
        cell: (e) => e.lastError || EMPTY_VALUE,
      },
      {
        header: "Next Attempt At",
        visibility: "optional",
        sortField: "nextAttemptAt",
        cell: (e) => <DateTime value={e.nextAttemptAt} className="text-on-surface-variant" />,
      },
      {
        header: "Body",
        visibility: "optional",
        cell: (e) => e.body,
      },
      {
        header: "Notification",
        visibility: "optional",
        cell: (e) => (e.notificationId ? `${e.notificationId.slice(0, 8)}…` : EMPTY_VALUE),
      },
      {
        header: "Created At",
        visibility: "optional",
        sortField: "createdAt",
        cell: (e) => <DateTime value={e.createdAt} className="text-on-surface-variant" />,
      },
      ...auditColumns<OutboundEmail>(names),
    ],
    [names, tenantNames, isAllTenantsView]
  );

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "auditOutboundEmails",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Emails" },
        ]}
      />
      <AuditTabs active="outbound-emails" />
      <AdminPageHeader
        title="Outbound Emails"
        icon={Mail}
        onRefresh={reload}
        refreshing={loading || refreshing}
        columnPicker={
          <ColumnPicker
            options={options}
            value={selected}
            onChange={setSelected}
            onReset={reset}
            customized={customized}
          />
        }
      />
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage="No notification email has been queued yet."
        emptyIcon={Mail}
        getRowKey={(e) => e.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={rows.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
    </AdminPageContainer>
  );
}
