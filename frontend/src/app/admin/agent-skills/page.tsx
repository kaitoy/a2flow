"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { type AgentSkill, deleteAgentSkill, listAgentSkills } from "@/lib/api";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<AgentSkill>[] = [
  {
    header: "Name",
    cell: (s) => <span className="font-medium">{s.name}</span>,
  },
  {
    header: "Repo URL",
    className: "max-w-[200px] truncate",
    cell: (s) => s.repo_url,
  },
  {
    header: "Repo Path",
    cell: (s) => s.repo_path || "—",
  },
  {
    header: "Description",
    className: "max-w-[200px] truncate",
    cell: (s) => s.description || "—",
  },
  {
    header: "Created At",
    cell: (s) => (
      <span className="text-on-surface-variant">{new Date(s.created_at).toLocaleDateString()}</span>
    ),
  },
];

export default function AgentSkillsPage() {
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgentSkills(LIMIT, offset);
      setSkills(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load agent skills");
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
      await deleteAgentSkill(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete agent skill");
    }
  }

  const columns: ColumnDef<AgentSkill>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      cell: (skill) => (
        <div className="flex gap-2">
          <Link href={`/admin/agent-skills/${skill.id}`} className="text-primary hover:underline">
            Edit
          </Link>
          <button
            type="button"
            onClick={() => handleDelete(skill.id, skill.name)}
            className="text-error hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-on-surface">Agent Skills</h1>
        <Link
          href="/admin/agent-skills/new"
          className="inline-flex cursor-pointer items-center rounded bg-primary-container px-4 py-2 text-sm font-medium text-on-primary-container transition-colors hover:bg-primary"
        >
          + Add skill
        </Link>
      </div>

      {error && (
        <div className="mb-4 rounded bg-error-container p-3 text-sm text-on-error-container">
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={skills}
        loading={loading}
        emptyMessage="No agent skills registered yet."
        getRowKey={(skill) => skill.id}
      />

      <div className="mt-4 flex gap-2">
        <Button
          variant="ghost"
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
        >
          ← Previous
        </Button>
        <Button
          variant="ghost"
          disabled={skills.length < LIMIT}
          onClick={() => setOffset((o) => o + LIMIT)}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
