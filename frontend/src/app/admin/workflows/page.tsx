"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import {
  type AgentSkill,
  type Workflow,
  deleteWorkflow,
  listAgentSkills,
  listWorkflows,
} from "@/lib/api";

const LIMIT = 20;

function buildColumns(
  skillMap: Map<string, string>,
  onDelete: (id: string, name: string) => void,
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
      cell: (w) => skillMap.get(w.agent_skill_id) ?? w.agent_skill_id,
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
          {new Date(w.created_at).toLocaleDateString()}
        </span>
      ),
    },
    {
      header: "Actions",
      cell: (w) => (
        <div className="flex gap-2">
          <Link href={`/admin/workflows/${w.id}`} className="text-primary hover:underline">
            Edit
          </Link>
          <button
            type="button"
            onClick={() => onDelete(w.id, w.name)}
            className="text-error hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [skillMap, setSkillMap] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, skills] = await Promise.all([
        listWorkflows(LIMIT, offset),
        listAgentSkills(1000, 0),
      ]);
      setWorkflows(data);
      setSkillMap(new Map((skills as AgentSkill[]).map((s) => [s.id, s.name])));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete(id: string, name: string) {
    if (!window.confirm(`Delete "${name}"?`)) return;
    try {
      await deleteWorkflow(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete workflow");
    }
  }

  return (
    <div className="p-8">
      <AdminPageHeader title="Workflows" addHref="/admin/workflows/new" addLabel="+ Add workflow" />
      <ErrorBanner error={error} />
      <DataTable
        columns={buildColumns(skillMap, handleDelete)}
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
    </div>
  );
}
