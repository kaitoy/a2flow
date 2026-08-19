/** @module WorkflowExecutionsPage — Admin list page for browsing executed WorkflowExecutions. */
"use client";

import { ClipboardList, ListChecks, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useUserNames } from "@/hooks/useUserNames";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import {
  deleteWorkflowExecution,
  listWorkflowExecutions,
  type WorkflowExecution,
  type WorkflowExecutionStatus,
} from "@/lib/api";

const LIMIT = 20;

/** Muted-to-vivid color per lifecycle state, matching the Approvals status treatment. */
const STATUS_STYLES: Record<WorkflowExecutionStatus, string> = {
  running: "text-on-surface-variant",
  completed: "text-accent",
  failed: "text-error",
};

/**
 * Build the table columns, resolving user ids to display names via `userMap`
 * and wiring the Actions column's Delete button to `onDelete`.
 */
function buildColumns(
  userMap: Map<string, string>,
  onDelete: (id: string, name: string) => void
): ColumnDef<WorkflowExecution>[] {
  return [
    idColumn<WorkflowExecution>(),
    {
      header: "Workflow",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (s) => (
        <Link
          href={`/admin/workflow-executions/${s.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.name}
        </Link>
      ),
    },
    {
      header: "Agent Skill",
      sortField: "agentSkillName",
      filterField: "agentSkillName",
      cell: (s) => s.agentSkillName,
    },
    {
      // Resolved from initiatorId to a display name; not sorted/filtered by raw id.
      header: "Initiator",
      cell: (s) =>
        s.initiatorId ? (
          <Link
            href={`/admin/users/${s.initiatorId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {userMap.get(s.initiatorId) ?? s.initiatorId}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      header: "Created At",
      sortField: "createdAt",
      visibility: "optional",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Status",
      sortField: "status",
      filterField: "status",
      filterOp: "eq",
      filterOptions: [
        { label: "Running", value: "running" },
        { label: "Completed", value: "completed" },
        { label: "Failed", value: "failed" },
      ],
      cell: (s) => (
        <span className={`font-medium capitalize ${STATUS_STYLES[s.status ?? "running"]}`}>
          {s.status ?? "running"}
        </span>
      ),
    },
    {
      header: "Finished At",
      cell: (s) =>
        s.finishedAt ? <DateTime value={s.finishedAt} className="text-on-surface-variant" /> : "—",
    },
    {
      header: "Description",
      visibility: "optional",
      cell: (s) => s.description || "—",
    },
    {
      header: "Agent Skill Repo URL",
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.agentSkillRepoUrl,
    },
    {
      header: "Agent Skill Repo Path",
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.agentSkillRepoPath || "—",
    },
    {
      header: "Agent Skill Commit SHA",
      visibility: "optional",
      className: "font-mono",
      cell: (s) => formatRevision(s.agentSkillCommitSha),
    },
    ...auditColumns<WorkflowExecution>(userMap),
    {
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (s) => (
        <div className="flex justify-center gap-2">
          <ActionIconButton
            icon={ClipboardList}
            label="View tasks"
            href={`/admin/workflow-executions/${s.id}/workflow-tasks`}
          />
          <ActionIconButton
            icon={MessageSquareText}
            label="Open workflow session"
            href={`/workflow-executions/${s.id}/session`}
          />
          <DeleteIconButton onClick={() => onDelete(s.id, s.name)} />
        </div>
      ),
    },
  ];
}

/** Admin list of WorkflowExecutions ordered by most recent first. */
export default function WorkflowExecutionsPage() {
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
  } = useTableQuery<WorkflowExecution>(listWorkflowExecutions, { limit: LIMIT });
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflowExecution(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  // Resolve user display names for the current page of sessions.
  const userMap = useUserNames(rows.flatMap((s) => [s.initiatorId, s.createdBy, s.updatedBy]));

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflowExecutions",
    buildColumns(userMap, handleDelete)
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflow Executions" }]} />
      <AdminPageHeader
        title="Workflow Executions"
        icon={ListChecks}
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
        emptyMessage="No workflow executions yet. Run a workflow to create one."
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
        title="Delete Workflow Execution"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
