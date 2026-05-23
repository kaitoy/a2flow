/** @module WorkflowsPage — Admin list page for managing workflows. */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
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
      cell: (w) => <span className="font-medium">{w.name}</span>,
    },
    {
      header: "Prompt",
      className: "max-w-[200px] truncate",
      cell: (w) => w.prompt,
    },
    {
      header: "Agent Skill",
      cell: (w) => skillMap.get(w.agentSkillId) ?? w.agentSkillId,
    },
    {
      header: "Description",
      className: "max-w-[200px] truncate",
      cell: (w) => w.description || "—",
    },
    {
      header: "Created At",
      cell: (w) => (
        <span className="text-on-surface-variant">
          {new Date(w.createdAt).toLocaleDateString()}
        </span>
      ),
    },
    {
      header: "Actions",
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
          <Link
            href={`/admin/workflows/${w.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Edit
          </Link>
          <button
            type="button"
            onClick={() => onDelete(w.id, w.name)}
            className="cursor-pointer text-error transition-colors hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];
}

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [skillMap, setSkillMap] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, skills] = await Promise.all([
        listWorkflows(LIMIT, offset),
        listAgentSkills(1000, 0),
      ]);
      setWorkflows(data);
      setSkillMap(new Map(skills.map((s) => [s.id, s.name])));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflow(confirmTarget.id);
      setConfirmTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete workflow");
      setConfirmTarget(null);
    }
  }

  async function handleRun(id: string) {
    setError(null);
    setRunningId(id);
    try {
      const workflowSession = await executeWorkflow(id);
      router.push(`/workflow-sessions/${workflowSession.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run workflow");
      setRunningId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-8">
      <AdminPageHeader title="Workflows" addHref="/admin/workflows/new" addLabel="+ Add workflow" />
      <ErrorBanner error={error} />
      <DataTable
        columns={buildColumns(skillMap, handleRun, runningId, handleDelete)}
        rows={workflows}
        loading={loading}
        emptyMessage="No workflows registered yet."
        getRowKey={(w) => w.id}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={workflows.length}
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
