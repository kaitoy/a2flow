/** @module NotificationList — The signed-in user's full notification history, with per-row read and delete actions. */
"use client";

import { Bell, Check } from "lucide-react";
import { useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { formatFullTimestamp, formatRelativeTime } from "@/components/ui/date-time";
import { Tooltip } from "@/components/ui/tooltip";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import {
  deleteNotification,
  listNotifications,
  type Notification,
  updateNotification,
} from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { markReadLocal, removeLocal } from "@/store/notificationsSlice";

/** Page size for the notification history. */
const LIMIT = 20;

/** Filter dropdown choices for the Type column, matching `NotificationType`. */
const TYPE_OPTIONS = [
  { value: "approval_request", label: "approval_request" },
  { value: "execution_completed", label: "execution_completed" },
  { value: "workflow_draft_ready", label: "workflow_draft_ready" },
  { value: "workflow_generation_failed", label: "workflow_generation_failed" },
];

/** Yes/No options for the Read column's boolean `eq` filter. */
const READ_FILTER_OPTIONS = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
];

/** Render a boolean cell as a checkmark or an em dash. */
function boolCell(value: boolean): string {
  return value ? "✓" : "—";
}

/**
 * The signed-in user's complete notification history — read items included —
 * rendered as a sortable, filterable table. Rendered on the dedicated
 * `/notifications` page, reachable from the account menu (see `UserMenu`).
 *
 * This is the counterpart to the toolbar bell's dropdown, which deliberately
 * shows only unread items and can only mark them read. Deleting a notification
 * for good happens here, where the user can still see what they are discarding.
 *
 * The list keeps its own query state rather than sharing the notifications Redux
 * slice: that slice holds the bell's unread page, and paging through the history
 * would otherwise clobber the badge. Read and delete actions instead dispatch
 * into the slice so the bell stays in step.
 */
export function NotificationList() {
  const dispatch = useAppDispatch();
  const { rows, loading, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<Notification>((query) => listNotifications(query), { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<Notification | null>(null);

  async function handleMarkRead(id: string) {
    try {
      await updateNotification(id, { read: true });
      dispatch(markReadLocal(id));
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteNotification(confirmTarget.id);
      dispatch(removeLocal(confirmTarget.id));
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<Notification>[] = [
    {
      header: "Title",
      sortField: "title",
      filterField: "title",
      visibility: "always",
      cell: (n) => n.title,
    },
    {
      header: "Type",
      sortField: "type",
      filterField: "type",
      filterOp: "eq",
      filterOptions: TYPE_OPTIONS,
      cell: (n) => n.type,
    },
    {
      header: "Read",
      sortField: "read",
      filterField: "read",
      filterOp: "eq",
      filterOptions: READ_FILTER_OPTIONS,
      className: "text-center",
      cell: (n) => boolCell(n.read ?? false),
    },
    {
      header: "Created",
      sortField: "createdAt",
      cell: (n) => (
        <Tooltip label={formatFullTimestamp(n.createdAt)}>
          <span>{formatRelativeTime(n.createdAt)}</span>
        </Tooltip>
      ),
    },
    {
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (n) => (
        <div className="flex justify-center gap-2">
          {!n.read && (
            <ActionIconButton
              icon={Check}
              label="Mark as read"
              onClick={() => void handleMarkRead(n.id)}
            />
          )}
          <DeleteIconButton onClick={() => setConfirmTarget(n)} />
        </div>
      ),
    },
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "notifications",
    columns
  );

  return (
    // This section is deliberately not wrapped in a `glass-panel-strong`:
    // `DataTable` brings its own glass panel, and nesting one inside another
    // breaks the elevation tiers described in DESIGN.md.
    <section className="flex flex-col gap-4">
      {/* There is no `AdminPageHeader` here to host the column picker, so the
          section title doubles as the toolbar row. */}
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
          Notifications
        </h2>
        <ColumnPicker
          options={options}
          value={selected}
          onChange={setSelected}
          onReset={reset}
          customized={customized}
        />
      </div>
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage="No notifications yet."
        emptyIcon={Bell}
        getRowKey={(n) => n.id}
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
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete notification"
        description={confirmTarget ? `Delete "${confirmTarget.title}"? This cannot be undone.` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </section>
  );
}
