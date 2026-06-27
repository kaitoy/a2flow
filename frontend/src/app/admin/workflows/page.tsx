/** @module WorkflowsPage — Admin list page for managing workflows. */
"use client";

import { Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useTableQuery } from "@/hooks/useTableQuery";
import {
  deleteWorkflow,
  executeWorkflow,
  listAgentSkills,
  listWorkflows,
  type Workflow,
} from "@/lib/api";

const LIMIT = 20;

function buildColumns(
  skillMap: Map<string, string>,
  onRun: (id: string) => void,
  runningId: string | null,
  onDelete: (id: string, name: string) => void
): ColumnDef<Workflow>[] {
  return [
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      cell: (w) => (
        <Link
          href={`/admin/workflows/${w.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {w.name}
        </Link>
      ),
    },
    {
      header: "Prompt",
      sortField: "prompt",
      filterField: "prompt",
      cell: (w) => w.prompt,
    },
    {
      // Resolved from agentSkillId to a display name; not a real column, so no sort/filter.
      header: "Agent Skill",
      cell: (w) => skillMap.get(w.agentSkillId) ?? w.agentSkillId,
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
          <button
            type="button"
            onClick={() => onRun(w.id)}
            disabled={runningId !== null}
            className="cursor-pointer text-accent transition-colors hover:underline disabled:cursor-wait disabled:opacity-50"
          >
            {runningId === w.id ? "Running…" : "Run"}
          </button>
          <DeleteIconButton onClick={() => onDelete(w.id, w.name)} />
        </div>
      ),
    },
  ];
}

export default function WorkflowsPage() {
  const router = useRouter();
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<Workflow>(listWorkflows, {
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
    <div className="mx-auto max-w-6xl p-8">
      <AdminPageHeader
        title="Workflows"
        icon={WorkflowIcon}
        addHref="/admin/workflows/new"
        addLabel="+ Add workflow"
        onRefresh={reload}
        refreshing={loading}
      />
      <ErrorBanner error={actionError ?? error} />
      <DataTable
        columns={buildColumns(skillMap, handleRun, runningId, handleDelete)}
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
    </div>
  );
}
