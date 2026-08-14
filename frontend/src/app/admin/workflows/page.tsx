/** @module WorkflowsPage — Admin list page for managing workflows. */
"use client";

import { Loader2, MessageSquareText, Play, Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tagsColumn } from "@/components/admin/tag-columns";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { Tooltip } from "@/components/ui/tooltip";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import {
  deleteWorkflow,
  executeWorkflow,
  listAgentSkills,
  listWorkflows,
  type Workflow,
  type WorkflowStatus,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import {
  canExecuteWorkflow,
  formatWorkflowStatusLabel,
  WORKFLOW_STATUS_DOT_CLASS,
  WORKFLOW_STATUSES,
  type WorkflowExecutePermissions,
} from "@/lib/workflow-status";

const LIMIT = 20;

/**
 * How often the list re-fetches while any workflow is still generating its
 * task templates. Generation runs in the background on the server, so nothing
 * its result here.
 */
const POLL_INTERVAL_MS = 2000;

/** Status dot plus label, matching the agent-skill table's status treatment. */
function StatusCell({ workflow }: { workflow: Workflow }) {
  const status = (workflow.status ?? "draft") as WorkflowStatus;
  const label = (
    <span className="flex items-center gap-2">
      <span
        className={`inline-block size-2 rounded-full ${WORKFLOW_STATUS_DOT_CLASS[status]}`}
        aria-hidden
      />
      <span className="capitalize">{formatWorkflowStatusLabel(status)}</span>
    </span>
  );
  // The failure reason is the whole point of the failed state, but it is a raw
  // error message — too long for a cell, so it lives in the tooltip.
  return workflow.generationError ? (
    <Tooltip label={workflow.generationError}>{label}</Tooltip>
  ) : (
    label
  );
}

function buildColumns(
  skillMap: Map<string, string>,
  onRun: (id: string, name: string) => void,
  runningId: string | null,
  onDelete: (id: string, name: string) => void,
  onOpenDesign: (id: string) => void,
  permissions: WorkflowExecutePermissions
): ColumnDef<Workflow>[] {
  return [
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      // Anyone who can edit or run a workflow has a reason to open its
      // detail page; everyone else sees a plain name.
      cell: (w) =>
        permissions.canEdit || permissions.canRun ? (
          <Link
            href={`/admin/workflows/${w.id}`}
            className="font-medium text-accent transition-colors hover:underline"
          >
            {w.name}
          </Link>
        ) : (
          <span className="font-medium text-on-surface">{w.name}</span>
        ),
    },
    {
      // Resolved from agentSkillId to a display name; not a real column, so no sort/filter.
      header: "Agent Skill",
      cell: (w) => (
        <Link
          href={`/admin/agent-skills/${w.agentSkillId}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {skillMap.get(w.agentSkillId) ?? w.agentSkillId}
        </Link>
      ),
    },
    {
      header: "Status",
      sortField: "status",
      filterField: "status",
      filterOp: "eq",
      filterOptions: WORKFLOW_STATUSES.map((s) => ({
        label: formatWorkflowStatusLabel(s),
        value: s,
      })),
      noTruncate: true,
      cell: (w) => <StatusCell workflow={w} />,
    },
    {
      header: "Description",
      sortField: "description",
      filterField: "description",
      // Falls back to the AI-generated summary, mirroring the workflow
      // session's own fallback rule (see WorkflowDetailPage).
      cell: (w) => w.description || w.generatedDescription || "—",
    },
    {
      header: "Created At",
      sortField: "createdAt",
      cell: (w) => <DateTime value={w.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Agent Skill Commit SHA",
      visibility: "optional",
      className: "font-mono",
      cell: (w) => formatRevision(w.agentSkillCommitSha),
    },
    ...auditColumns<Workflow>(),
    {
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (w) => (
        <div className="flex justify-center gap-2">
          {permissions.canEdit && (
            <ActionIconButton
              icon={MessageSquareText}
              label="Open design session"
              onClick={() => onOpenDesign(w.id)}
              disabled={w.status === "generating"}
            />
          )}
          {permissions.canRun && (
            <ActionIconButton
              icon={runningId === w.id ? Loader2 : Play}
              label="Run"
              onClick={() => onRun(w.id, w.name)}
              // Published workflows are executable by anyone with Run access;
              // drafts are executable only by someone who can also edit
              // workflows (developer/super_admin), for pre-publish testing.
              disabled={runningId !== null || !canExecuteWorkflow(w.status, permissions)}
              spinning={runningId === w.id}
            />
          )}
          {permissions.canEdit && <DeleteIconButton onClick={() => onDelete(w.id, w.name)} />}
        </div>
      ),
    },
  ];
}

export default function WorkflowsPage() {
  const router = useRouter();
  const canRun = useHasRole(Role.REQUESTER, Role.DEVELOPER);
  const canEdit = useHasRole(Role.DEVELOPER);
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
    tagIds,
    setTagIds,
    reload,
  } = useTableQuery<Workflow>(listWorkflows, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const [skillMap, setSkillMap] = useState<Map<string, string>>(new Map());
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [runTarget, setRunTarget] = useState<{ id: string; name: string } | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  // Load the agent-skill name map once, to label the Agent Skill column.
  useEffect(() => {
    listAgentSkills({ limit: 1000 })
      .then((skills) => setSkillMap(new Map(skills.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Non-fatal: the column falls back to showing the raw skill id.
      });
  }, []);

  const anyGenerating = rows.some((w) => w.status === "generating");

  // Design generation settles server-side with nothing to notify us, so poll
  // until every row has landed on draft or failed, then stop. Silently: only
  // the cells that changed re-render.
  useEffect(() => {
    if (!anyGenerating) return;
    const timer = setInterval(() => {
      void reload({ silent: true });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [anyGenerating, reload]);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflow(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  function handleRun(id: string, name: string) {
    setRunTarget({ id, name });
  }

  async function executeRun() {
    if (!runTarget) return;
    const id = runTarget.id;
    setRunTarget(null);
    setRunningId(id);
    try {
      const workflowExecution = await executeWorkflow(id);
      router.push(`/workflow-executions/${workflowExecution.id}/session`);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setRunningId(null);
    }
  }

  function handleOpenDesign(id: string) {
    // A design session has no id of its own — it is addressed by its workflow.
    router.push(`/workflows/${encodeURIComponent(id)}/design-session`);
  }

  const columns = [
    ...buildColumns(skillMap, handleRun, runningId, handleDelete, handleOpenDesign, {
      canRun,
      canEdit,
    }),
    tagsColumn<Workflow>((w) => w.tagIds, tagsById),
  ];
  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflows",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflows" }]} />
      <AdminPageHeader
        title="Workflows"
        icon={WorkflowIcon}
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
        emptyMessage="No workflows registered yet."
        emptyIcon={WorkflowIcon}
        getRowKey={(w) => w.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
        tagIds={tagIds}
        onTagIdsChange={setTagIds}
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
        title="Delete Workflow"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
      <ConfirmDialog
        open={runTarget !== null}
        title="Run Workflow"
        description={runTarget ? `Run "${runTarget.name}"? This starts a new execution.` : ""}
        confirmLabel="Run"
        confirmVariant="primary"
        onConfirm={executeRun}
        onCancel={() => setRunTarget(null)}
      />
    </AdminPageContainer>
  );
}
