/** @module WorkflowTasksPage — Admin list page for WorkflowTasks belonging to a single WorkflowSession. */
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Select } from "@/components/ui/select";
import { WorkflowTaskGraph } from "@/components/workflow-task-graph";
import {
  deleteWorkflowTask,
  listMcpServers,
  listWorkflowTasks,
  updateWorkflowTask,
  type WorkflowTask,
  type WorkflowTaskStatus,
} from "@/lib/api";
import {
  formatStatusLabel,
  STATUS_DOT_CLASS,
  WORKFLOW_TASK_STATUSES,
} from "@/lib/workflow-task-status";

/** Page size for the paginated table view. */
const LIMIT = 20;
/** Upper bound (backend maximum) used to fetch the whole DAG for the graph view. */
const GRAPH_LIMIT = 1000;
/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/** Which representation of the tasks is currently shown. */
type View = "table" | "graph";

const VIEW_OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

/** Small colored dot used next to the status select for quick visual scanning. */
function StatusDot({ status }: { status: WorkflowTaskStatus }) {
  return (
    <span className={`inline-block size-2 rounded-full ${STATUS_DOT_CLASS[status]}`} aria-hidden />
  );
}

/** Pill showing a single related item (dependency or bound tool) by label. */
function Chip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-full glass-panel px-2 py-0.5 text-xs text-on-surface-variant">
      {label}
    </span>
  );
}

function buildColumns(
  wsId: string,
  titleById: Map<string, string>,
  serverNameById: Map<string, string>,
  onStatusChange: (taskId: string, status: WorkflowTaskStatus) => void,
  onDelete: (id: string, title: string) => void
): ColumnDef<WorkflowTask>[] {
  return [
    {
      header: "#",
      className: "w-12 text-on-surface-variant",
      cell: (t) => t.position ?? 0,
    },
    {
      header: "Title",
      cell: (t) => <span className="font-medium">{t.title}</span>,
    },
    {
      header: "Description",
      className: "max-w-[280px] truncate",
      cell: (t) => t.description || "—",
    },
    {
      header: "Depends on",
      cell: (t) => {
        const deps = t.dependsOnIds ?? [];
        if (deps.length === 0) return <span className="text-on-surface-variant">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {deps.map((id) => (
              <Chip key={id} label={titleById.get(id) ?? `${id.slice(0, 8)}…`} />
            ))}
          </div>
        );
      },
    },
    {
      header: "Tools",
      cell: (t) => {
        const bindings = t.toolBindings ?? [];
        if (bindings.length === 0) return <span className="text-on-surface-variant">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {bindings.map((b) => (
              <Chip
                key={`${b.mcpServerId}:${b.toolName}`}
                label={`${
                  serverNameById.get(b.mcpServerId) ?? `${b.mcpServerId.slice(0, 8)}…`
                }: ${b.toolName}`}
              />
            ))}
          </div>
        );
      },
    },
    {
      header: "Status",
      cell: (t) => (
        <div className="flex items-center gap-2">
          <StatusDot status={t.status ?? "pending"} />
          <Select
            value={t.status ?? "pending"}
            onChange={(e) => onStatusChange(t.id, e.target.value as WorkflowTaskStatus)}
            aria-label={`Status for ${t.title}`}
          >
            {WORKFLOW_TASK_STATUSES.map((s) => (
              <option key={s} value={s}>
                {formatStatusLabel(s)}
              </option>
            ))}
          </Select>
        </div>
      ),
    },
    {
      header: "Actions",
      cell: (t) => (
        <div className="flex gap-2">
          <Link
            href={`/admin/workflow-sessions/${wsId}/workflow-tasks/${t.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Edit
          </Link>
          <button
            type="button"
            onClick={() => onDelete(t.id, t.title)}
            className="cursor-pointer text-error transition-colors hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];
}

/** Admin list of WorkflowTasks for the WorkflowSession in the URL parameters. */
export default function WorkflowTasksPage() {
  const { wsId } = useParams<{ wsId: string }>();
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<View>("table");
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; title: string } | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The graph needs every task so dependency edges are not cut across pages.
      const data =
        view === "graph"
          ? await listWorkflowTasks(wsId, GRAPH_LIMIT, 0)
          : await listWorkflowTasks(wsId, LIMIT, offset);
      setTasks(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflow tasks");
    } finally {
      setLoading(false);
    }
  }, [wsId, offset, view]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    listMcpServers(SERVER_LIMIT, 0)
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, []);

  async function handleStatusChange(taskId: string, status: WorkflowTaskStatus) {
    setError(null);
    try {
      const updated = await updateWorkflowTask(taskId, { status });
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  }

  function handleDelete(id: string, title: string) {
    setConfirmTarget({ id, title });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflowTask(confirmTarget.id);
      setConfirmTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete task");
      setConfirmTarget(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-8">
      <Link
        href="/admin/workflow-sessions"
        className="mb-4 inline-block text-xs text-on-surface-variant transition-colors hover:text-accent"
      >
        ← Back to sessions
      </Link>
      <AdminPageHeader
        title="Workflow Tasks"
        addHref={`/admin/workflow-sessions/${wsId}/workflow-tasks/new`}
        addLabel="+ Add task"
      />
      <div className="mb-4">
        <SegmentedControl
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="Task view"
        />
      </div>
      <ErrorBanner error={error} />
      {view === "graph" ? (
        <WorkflowTaskGraph tasks={tasks} />
      ) : (
        <>
          <DataTable
            columns={buildColumns(
              wsId,
              new Map(tasks.map((t) => [t.id, t.title])),
              serverNameById,
              handleStatusChange,
              handleDelete
            )}
            rows={tasks}
            loading={loading}
            emptyMessage="No tasks for this session yet."
            getRowKey={(t) => t.id}
          />
          <PaginationControls
            offset={offset}
            limit={LIMIT}
            count={tasks.length}
            onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
            onNext={() => setOffset((o) => o + LIMIT)}
          />
        </>
      )}
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete Workflow Task"
        description={confirmTarget ? `Delete "${confirmTarget.title}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}
