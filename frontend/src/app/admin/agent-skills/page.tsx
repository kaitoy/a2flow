"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
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
    cell: (s) => s.repoUrl,
  },
  {
    header: "Repo Path",
    cell: (s) => s.repoPath || "—",
  },
  {
    header: "Description",
    className: "max-w-[200px] truncate",
    cell: (s) => s.description || "—",
  },
  {
    header: "Created At",
    cell: (s) => (
      <span className="text-on-surface-variant">{new Date(s.createdAt).toLocaleDateString()}</span>
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
      <AdminPageHeader
        title="Agent Skills"
        addHref="/admin/agent-skills/new"
        addLabel="+ Add skill"
      />
      <ErrorBanner error={error} />
      <DataTable
        columns={columns}
        rows={skills}
        loading={loading}
        emptyMessage="No agent skills registered yet."
        getRowKey={(skill) => skill.id}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={skills.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
    </div>
  );
}
