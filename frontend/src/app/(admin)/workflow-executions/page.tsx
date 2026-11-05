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
import { tagsColumn } from "@/components/admin/tag-columns";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { WorkflowExecutionStatusLabel } from "@/components/admin/workflow-execution-status";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  BOOL_FILTER_OPTIONS,
  boolCell,
  type ColumnDef,
  DataTable,
} from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTenantNames, useUserNames, useWorkflowNames } from "@/hooks/useNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useT } from "@/i18n/provider";
import type { Translator } from "@/i18n/translate";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import {
  deleteWorkflowExecution,
  listWorkflowExecutions,
  type Tag,
  type WorkflowExecution,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

/**
 * Build the table columns, resolving user ids to display names via `userMap`,
 * workflow ids to their current names via `workflowMap`, and tag ids to their
 * chips via `tagsById`, and wiring the Actions column's Delete button to
 * `onDelete`. The Delete button only renders when `isAdmin` is true — the
 * backend restricts deletion to admins and super admins.
 */
function buildColumns(
  userMap: Map<string, string>,
  workflowMap: Map<string, string>,
  onDelete: (id: string, name: string) => void,
  isAdmin: boolean,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean,
  tagsById: Map<string, Tag>,
  canViewPrompt: boolean,
  t: Translator
): ColumnDef<WorkflowExecution>[] {
  return [
    ...(isAllTenantsView ? [tenantColumn<WorkflowExecution>(tenantNames)] : []),
    idColumn<WorkflowExecution>(),
    {
      header: "common.name" as const,
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (s) => (
        <Link
          href={`/workflow-executions/${s.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.name}
        </Link>
      ),
    },
    {
      // Resolved from workflowId to the workflow's current name via workflowMap;
      // not sorted/filtered by the raw id. Falls back to the id, then an em dash
      // once the run's workflow has been deleted (workflowId is null).
      header: "workflowExecutions.workflow",
      visibility: "optional",
      cell: (s) =>
        s.workflowId ? (
          <Link
            href={`/workflows/${s.workflowId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {workflowMap.get(s.workflowId) ?? s.workflowId}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      header: "common.status" as const,
      sortField: "status",
      filterField: "status",
      filterOp: "eq",
      filterOptions: [
        { label: t("workflowExecutions.running"), value: "running" },
        { label: t("workflowExecutions.scheduled"), value: "scheduled" },
        { label: t("workflowExecutions.completed"), value: "completed" },
        { label: t("common.failed"), value: "failed" },
      ],
      noTruncate: true,
      cell: (s) => <WorkflowExecutionStatusLabel status={s.status} />,
    },
    {
      // A run started from a still-draft workflow — a pre-publish test run. It is
      // excluded from the operations metrics; the filter lets an operator hide
      // these from the list too. Off by default: only the pre-publish test runs
      // of a few developers, not something most operators need on screen.
      header: "workflowExecutions.draft",
      sortField: "isDraft",
      filterField: "isDraft",
      filterOp: "eq",
      filterOptions: BOOL_FILTER_OPTIONS,
      visibility: "optional",
      className: "text-center",
      cell: (s) => boolCell(s.isDraft ?? false),
    },
    {
      // A draft run that stubbed some of its tools. Not sortable or filterable:
      // toolMocks is a JSON column, so there is no scalar for the list query to
      // order or compare against.
      header: "common.mocked",
      visibility: "optional",
      noTruncate: true,
      className: "text-center",
      cell: (s) =>
        s.toolMocks && s.toolMocks.length > 0 ? <Badge>{t("common.mocked")}</Badge> : null,
    },
    {
      // Resolved from initiatorId to a display name; not sorted/filtered by raw id.
      header: "workflowExecutions.initiator",
      cell: (s) =>
        s.initiatorId ? (
          <Link
            href={`/users/${s.initiatorId}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {userMap.get(s.initiatorId) ?? s.initiatorId}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      header: "common.createdAt" as const,
      sortField: "createdAt",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "workflowExecutions.finishedAt" as const,
      visibility: "optional",
      cell: (s) =>
        s.finishedAt ? <DateTime value={s.finishedAt} className="text-on-surface-variant" /> : "—",
    },
    // The backend blanks a run's prompt for anyone else, so the column would be empty.
    ...(canViewPrompt
      ? [
          {
            header: "common.prompt" as const,
            visibility: "optional" as const,
            cell: (s: WorkflowExecution) => s.prompt || "—",
          },
        ]
      : []),
    {
      header: "common.agentSkill" as const,
      sortField: "agentSkillName",
      filterField: "agentSkillName",
      visibility: "optional",
      cell: (s) => (
        <Link
          href={`/agent-skills/${s.agentSkillId}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.agentSkillName}
        </Link>
      ),
    },
    {
      header: "workflowExecutions.agentSkillRepoUrl" as const,
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.agentSkillRepoUrl,
    },
    {
      header: "workflowExecutions.agentSkillRepoPath" as const,
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.agentSkillRepoPath || "—",
    },
    {
      header: "workflowExecutions.agentSkillCommit" as const,
      visibility: "optional",
      className: "font-mono",
      cell: (s) => formatRevision(s.agentSkillCommitSha),
    },
    ...auditColumns<WorkflowExecution>(userMap),
    tagsColumn<WorkflowExecution>((s) => s.tagIds, tagsById),
    {
      header: "common.actions" as const,
      noTruncate: true,
      visibility: "always",
      cell: (s) => (
        <div className="flex justify-center gap-2">
          <ActionIconButton
            icon={ClipboardList}
            label={t("workflowExecutions.viewTasks")}
            href={`/workflow-executions/${s.id}/workflow-tasks`}
          />
          <ActionIconButton
            icon={MessageSquareText}
            label={t("common.openWorkflowSession")}
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
  const t = useT();
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
  const canViewPrompt = useHasRole(Role.ADMIN, Role.DEVELOPER, Role.REVIEWER);

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
  // Resolve each run's parent workflow to its current name for the Workflow column.
  const workflowMap = useWorkflowNames(rows.map((s) => s.workflowId));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((s) => s.tenantId) : []);
  const { byId: tagsById } = useTags();

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflowExecutions",
    buildColumns(
      userMap,
      workflowMap,
      handleDelete,
      isAdmin,
      tenantNames,
      isAllTenantsView,
      tagsById,
      canViewPrompt,
      t
    )
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[{ label: t("common.home"), href: "/" }, { label: t("common.workflowExecutions") }]}
      />
      <AdminPageHeader
        title={t("common.workflowExecutions")}
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
        emptyMessage={t("workflowExecutions.noWorkflowExecutionsYetRunAWorkflow")}
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
        title={t("workflowExecutions.deleteWorkflowExecution")}
        description={confirmTarget ? t("common.deleteName", { name: confirmTarget.name }) : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
