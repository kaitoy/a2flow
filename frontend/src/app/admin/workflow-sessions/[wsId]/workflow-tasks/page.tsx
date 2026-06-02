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
import { Select } from "@/components/ui/select";
import {
  deleteWorkflowTask,
  listWorkflowTasks,
  updateWorkflowTask,
  type WorkflowTask,
  type WorkflowTaskStatus,
} from "@/lib/api";

const LIMIT = 20;

const STATUS_OPTIONS: WorkflowTaskStatus[] = [
  "pending",
  "in_progress",
  "completed",
  "failed",
  "skipped",
];

const STATUS_DOT: Record<WorkflowTaskStatus, string> = {
  pending: "bg-on-surface-variant",
  in_progress: "bg-accent",
  completed: "bg-green-500/80",
  failed: "bg-error",
  skipped: "bg-on-surface-variant/50",
};

/** Small colored dot used next to the status select for quick visual scanning. */
function StatusDot({ status }: { status: WorkflowTaskStatus }) {
  return <span className={`inline-block size-2 rounded-full ${STATUS_DOT[status]}`} aria-hidden />;
}

/** Pill showing a single dependency, resolved to its task title when known. */
function DependencyChip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-full glass-panel px-2 py-0.5 text-xs text-on-surface-variant">
      {label}
    </span>
  );
}

function buildColumns(
  wsId: string,
  titleById: Map<string, string>,
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
              <DependencyChip key={id} label={titleById.get(id) ?? `${id.slice(0, 8)}…`} />
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
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
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
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; title: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflowTasks(wsId, LIMIT, offset);
      setTasks(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflow tasks");
    } finally {
      setLoading(false);
    }
  }, [wsId, offset]);

  useEffect(() => {
    load();
  }, [load]);

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
      <ErrorBanner error={error} />
      <DataTable
        columns={buildColumns(
          wsId,
          new Map(tasks.map((t) => [t.id, t.title])),
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
