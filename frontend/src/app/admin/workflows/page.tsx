/** @module WorkflowsPage — Admin list page for managing workflows. */
"use client";

import { Loader2, Play, Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Tooltip } from "@/components/ui/tooltip";
import { useTableQuery } from "@/hooks/useTableQuery";
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
  formatWorkflowStatusLabel,
  WORKFLOW_STATUS_DOT_CLASS,
  WORKFLOW_STATUSES,
} from "@/lib/workflow-status";

const LIMIT = 20;

/**
 * How often the list re-fetches while any workflow is still generating its
 * plan. Generation runs in the background on the server, so nothing pushes
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

/** Per-role capabilities driving which row actions the table renders. */
interface WorkflowPermissions {
  /** True when the viewer may execute workflows (`requester`). */
  canRun: boolean;
  /** True when the viewer may create, edit, and delete workflows (`developer`). */
  canEdit: boolean;
}

function buildColumns(
  skillMap: Map<string, string>,
  onRun: (id: string) => void,
  runningId: string | null,
  onDelete: (id: string, name: string) => void,
  permissions: WorkflowPermissions
): ColumnDef<Workflow>[] {
  return [
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      // Only developers can open the edit form; everyone else sees a plain name.
      cell: (w) =>
        permissions.canEdit ? (
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
      cell: (w) => skillMap.get(w.agentSkillId) ?? w.agentSkillId,
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
      cell: (w) => w.description || "—",
    },
    {
      header: "Created At",
      sortField: "createdAt",
      cell: (w) => <DateTime value={w.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Actions",
      noTruncate: true,
      cell: (w) => (
        <div className="flex gap-2">
          {permissions.canRun && (
            <ActionIconButton
              icon={runningId === w.id ? Loader2 : Play}
              label="Run"
              onClick={() => onRun(w.id)}
              // Only published workflows are executable; drafts are still
              // being planned or awaiting review.
              disabled={runningId !== null || w.status !== "published"}
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
  const canRun = useHasRole(Role.REQUESTER);
  const canEdit = useHasRole(Role.DEVELOPER);
  const {
    rows,
    loading,
    refreshing,
    error,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload,
  } = useTableQuery<Workflow>(listWorkflows, {
    limit: LIMIT,
    errorMessage: "Failed to load workflows",
  });
  const [skillMap, setSkillMap] = useState<Map<string, string>>(new Map());
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
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

  // Plan generation settles server-side with nothing to notify us, so poll
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
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete workflow");
      setConfirmTarget(null);
    }
  }

  async function handleRun(id: string) {
    setActionError(null);
    setRunningId(id);
    try {
      const workflowSession = await executeWorkflow(id);
      router.push(`/workflow-sessions/${workflowSession.id}`);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to run workflow");
      setRunningId(null);
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Workflows" }]} />
      <AdminPageHeader
        title="Workflows"
        icon={WorkflowIcon}
        onRefresh={reload}
        refreshing={loading || refreshing}
      />
      <div className="mb-4">
        <ErrorBanner error={actionError ?? error} />
      </div>
      <DataTable
        columns={buildColumns(skillMap, handleRun, runningId, handleDelete, {
          canRun,
          canEdit,
        })}
        rows={rows}
        loading={loading}
        emptyMessage="No workflows registered yet."
        emptyIcon={WorkflowIcon}
        getRowKey={(w) => w.id}
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
        title="Delete Workflow"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
