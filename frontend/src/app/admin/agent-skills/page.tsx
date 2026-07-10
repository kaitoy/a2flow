/** @module AgentSkillsPage — Admin list page for managing agent skills. */
"use client";

import { Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { ErrorBanner } from "@/components/ui/error-banner";
import { useTableQuery } from "@/hooks/useTableQuery";
import { type AgentSkill, deleteAgentSkill, listAgentSkills } from "@/lib/api";

const LIMIT = 20;

const STATIC_COLUMNS: ColumnDef<AgentSkill>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    cell: (s) => (
      <Link
        href={`/admin/agent-skills/${s.id}`}
        className="font-medium text-accent transition-colors hover:underline"
      >
        {s.name}
      </Link>
    ),
  },
  {
    header: "Repo URL",
    sortField: "repoUrl",
    filterField: "repoUrl",
    className: "font-mono",
    cell: (s) => s.repoUrl,
  },
  {
    header: "Repo Path",
    sortField: "repoPath",
    filterField: "repoPath",
    className: "font-mono",
    cell: (s) => s.repoPath || "—",
  },
  {
    header: "Description",
    sortField: "description",
    filterField: "description",
    cell: (s) => s.description || "—",
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
  },
];

export default function AgentSkillsPage() {
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<AgentSkill>(listAgentSkills, {
      limit: LIMIT,
      errorMessage: "Failed to load agent skills",
    });
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteAgentSkill(confirmTarget.id);
      setConfirmTarget(null);
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete agent skill");
      setConfirmTarget(null);
    }
  }

  const columns: ColumnDef<AgentSkill>[] = [
    ...STATIC_COLUMNS,
    {
      header: "Actions",
      noTruncate: true,
      cell: (skill) => (
        <div className="flex gap-2">
          <DeleteIconButton onClick={() => handleDelete(skill.id, skill.name)} />
        </div>
      ),
    },
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Agent Skills" }]} />
      <AdminPageHeader
        title="Agent Skills"
        icon={Wand2}
        addHref="/admin/agent-skills/new"
        addLabel="+ Add skill"
        onRefresh={reload}
        refreshing={loading}
      />
      <div className="mb-4">
        <ErrorBanner error={actionError ?? error} />
      </div>
      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        emptyMessage="No agent skills registered yet."
        emptyIcon={Wand2}
        getRowKey={(skill) => skill.id}
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
        title="Delete Agent Skill"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
