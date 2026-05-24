/** @module WorkflowSessionsPage — Admin list page for browsing executed WorkflowSessions. */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { listWorkflowSessions, type WorkflowSession } from "@/lib/api";

const LIMIT = 20;

function buildColumns(): ColumnDef<WorkflowSession>[] {
  return [
    {
      header: "Workflow",
      cell: (s) => <span className="font-medium">{s.workflowName}</span>,
    },
    {
      header: "Agent Skill",
      cell: (s) => s.agentSkillName,
    },
    {
      header: "User",
      cell: (s) => s.userId || "—",
    },
    {
      header: "Created At",
      cell: (s) => (
        <span className="text-on-surface-variant">
          {new Date(s.createdAt).toLocaleString()}
        </span>
      ),
    },
    {
      header: "Actions",
      cell: (s) => (
        <div className="flex gap-2">
          <Link
            href={`/admin/workflow-sessions/${s.id}/workflow-tasks`}
            className="text-accent transition-colors hover:underline"
          >
            View tasks
          </Link>
          <Link
            href={`/workflow-sessions/${s.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Open chat
          </Link>
        </div>
      ),
    },
  ];
}

/** Admin list of WorkflowSessions ordered by most recent first. */
export default function WorkflowSessionsPage() {
  const [sessions, setSessions] = useState<WorkflowSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflowSessions(LIMIT, offset);
      setSessions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflow sessions");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-6xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        Workflow Sessions
      </h1>
      <ErrorBanner error={error} />
      <DataTable
        columns={buildColumns()}
        rows={sessions}
        loading={loading}
        emptyMessage="No workflow sessions yet. Run a workflow to create one."
        getRowKey={(s) => s.id}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={sessions.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
    </div>
  );
}
