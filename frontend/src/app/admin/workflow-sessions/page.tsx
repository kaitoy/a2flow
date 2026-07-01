/** @module WorkflowSessionsPage — Admin list page for browsing executed WorkflowSessions. */
"use client";

import { ListChecks, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useTableQuery } from "@/hooks/useTableQuery";
import {
  deleteWorkflowSession,
  getUserNames,
  listWorkflowSessions,
  type WorkflowSession,
} from "@/lib/api";

const LIMIT = 20;

/**
 * Build the table columns, resolving user ids to display names via `userMap`
 * and wiring the Actions column's Delete button to `onDelete`.
 */
function buildColumns(
  userMap: Map<string, string>,
  onDelete: (id: string, name: string) => void
): ColumnDef<WorkflowSession>[] {
  return [
    {
      header: "Workflow",
      sortField: "workflowName",
      filterField: "workflowName",
      cell: (s) => <span className="font-medium">{s.workflowName}</span>,
    },
    {
      header: "Agent Skill",
      sortField: "agentSkillName",
      filterField: "agentSkillName",
      cell: (s) => s.agentSkillName,
    },
    {
      // Resolved from userId to a display name; not sorted/filtered by raw id.
      header: "User",
      cell: (s) =>
        s.userId ? (
          <Link
            href={`/admin/users/${s.userId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {userMap.get(s.userId) ?? s.userId}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      header: "Created At",
      sortField: "createdAt",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Actions",
      noTruncate: true,
      cell: (s) => (
        <div className="flex gap-2">
          <ActionIconButton
            icon={ListChecks}
            label="View tasks"
            href={`/admin/workflow-sessions/${s.id}/workflow-tasks`}
          />
          <ActionIconButton
            icon={MessageSquare}
            label="Open chat"
            href={`/workflow-sessions/${s.id}`}
          />
          <DeleteIconButton onClick={() => onDelete(s.id, s.workflowName)} />
        </div>
      ),
    },
  ];
}

/** Admin list of WorkflowSessions ordered by most recent first. */
export default function WorkflowSessionsPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<WorkflowSession>(listWorkflowSessions, {
      limit: LIMIT,
      errorMessage: "Failed to load workflow sessions",
    });
  const [userMap, setUserMap] = useState<Map<string, string>>(new Map());
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflowSession(confirmTarget.id);
      setConfirmTarget(null);
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete workflow session");
      setConfirmTarget(null);
    }
  }

  // Resolve user display names for the current page of sessions.
  useEffect(() => {
    const ids = rows.map((s) => s.userId).filter((id): id is string => !!id);
    if (ids.length === 0) return;
    getUserNames(ids)
      .then(setUserMap)
      .catch(() => {
        // Non-fatal: the column falls back to showing the raw user id.
      });
  }, [rows]);

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflow Sessions" }]} />
      <AdminPageHeader
        title="Workflow Sessions"
        icon={ListChecks}
        onRefresh={reload}
        refreshing={loading}
      />
      <ErrorBanner error={actionError ?? error} />
      <DataTable
        columns={buildColumns(userMap, handleDelete)}
        rows={rows}
        loading={loading}
        emptyMessage="No workflow sessions yet. Run a workflow to create one."
        emptyIcon={ListChecks}
        getRowKey={(s) => s.id}
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
        title="Delete Workflow Session"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
