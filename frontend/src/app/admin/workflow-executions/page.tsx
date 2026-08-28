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
import { tenantColumn } from "@/components/admin/tenant-columns";
import { WorkflowExecutionStatusLabel } from "@/components/admin/workflow-execution-status";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { BOOL_FILTER_OPTIONS, type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import { deleteWorkflowExecution, listWorkflowExecutions, type WorkflowExecution } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

/**
 * Build the table columns, resolving user ids to display names via `userMap`
 * and wiring the Actions column's Delete button to `onDelete`. The Delete
 * button only renders when `isAdmin` is true — the backend restricts
 * deletion to admins and super admins.
 */
function buildColumns(
  userMap: Map<string, string>,
  onDelete: (id: string, name: string) => void,
  isAdmin: boolean,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<WorkflowExecution>[] {
  return [
    idColumn<WorkflowExecution>(),
    {
      header: "Name",
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
      header: "Status",
      sortField: "status",
      filterField: "status",
      filterOp: "eq",
      filterOptions: [
        { label: "Running", value: "running" },
        { label: "Completed", value: "completed" },
        { label: "Failed", value: "failed" },
      ],
      noTruncate: true,
      cell: (s) => <WorkflowExecutionStatusLabel status={s.status} />,
    },
    {
      // A run started from a still-draft workflow — a pre-publish test run. It is
      // excluded from the operations metrics; the filter lets an operator hide
      // these from the list too.
      header: "Draft",
      sortField: "isDraft",
      filterField: "isDraft",
      filterOp: "eq",
      filterOptions: BOOL_FILTER_OPTIONS,
      noTruncate: true,
      className: "text-center",
      cell: (s) => (s.isDraft ? <Badge>Draft</Badge> : null),
    },
    {
      // A draft run that stubbed some of its tools. Not sortable or filterable:
      // toolMocks is a JSON column, so there is no scalar for the list query to
      // order or compare against.
      header: "Mocked",
      visibility: "optional",
      noTruncate: true,
      className: "text-center",
      cell: (s) => (s.toolMocks && s.toolMocks.length > 0 ? <Badge>Mocked</Badge> : null),
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
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Finished At",
      visibility: "optional",
      cell: (s) =>
        s.finishedAt ? <DateTime value={s.finishedAt} className="text-on-surface-variant" /> : "—",
    },
    {
      header: "Description",
      visibility: "optional",
      cell: (s) => s.description || "—",
    },
    {
      header: "Agent Skill",
      sortField: "agentSkillName",
      filterField: "agentSkillName",
      visibility: "optional",
      cell: (s) => (
        <Link
          href={`/admin/agent-skills/${s.agentSkillId}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.agentSkillName}
        </Link>
      ),
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
      header: "Agent Skill Commit",
      visibility: "optional",
      className: "font-mono",
      cell: (s) => formatRevision(s.agentSkillCommitSha),
    },
    ...(isAllTenantsView ? [tenantColumn<WorkflowExecution>(tenantNames)] : []),
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
          {isAdmin && <DeleteIconButton onClick={() => onDelete(s.id, s.name)} />}
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
  const isAdmin = useHasRole(Role.ADMIN);

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
  const isAllTenantsView = useIsAllTenantsView();
  const tenantNames = useTenantNames(rows.map((s) => s.tenantId));

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflowExecutions",
    buildColumns(userMap, handleDelete, isAdmin, tenantNames, isAllTenantsView)
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
