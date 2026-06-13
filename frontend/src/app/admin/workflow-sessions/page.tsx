/** @module WorkflowSessionsPage — Admin list page for browsing executed WorkflowSessions. */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { getUserNames, listWorkflowSessions, type WorkflowSession } from "@/lib/api";

const LIMIT = 20;

function buildColumns(userMap: Map<string, string>): ColumnDef<WorkflowSession>[] {
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
      cell: (s) => (s.userId ? (userMap.get(s.userId) ?? s.userId) : "—"),
    },
    {
      header: "Created At",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
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
  const [userMap, setUserMap] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflowSessions(LIMIT, offset);
      setSessions(data);
      setUserMap(await getUserNames(data.map((s) => s.userId).filter((id): id is string => !!id)));
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
      <AdminPageHeader title="Workflow Sessions" />
      <ErrorBanner error={error} />
      <DataTable
        columns={buildColumns(userMap)}
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
