/** @module AgentSkillsPage — Admin list page for managing agent skills. */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { ErrorBanner } from "@/components/admin/error-banner";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

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

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteAgentSkill(confirmTarget.id);
      setConfirmTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete agent skill");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<AgentSkill>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      cell: (skill) => (
        <div className="flex gap-2">
          <Link
            href={`/admin/agent-skills/${skill.id}`}
            className="text-accent transition-colors hover:underline"
          >
            Edit
          </Link>
          <button
            type="button"
            onClick={() => handleDelete(skill.id, skill.name)}
            className="cursor-pointer text-error transition-colors hover:underline"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl p-8">
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
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete Agent Skill"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}
