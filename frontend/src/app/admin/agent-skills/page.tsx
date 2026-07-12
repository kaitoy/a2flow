/** @module AgentSkillsPage — Admin list page for managing agent skills. */
"use client";

import { RefreshCw, Wand2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Tooltip } from "@/components/ui/tooltip";
import { useTableQuery } from "@/hooks/useTableQuery";
import {
  formatRevision,
  formatSyncStatusLabel,
  SYNC_STATUS_DOT_CLASS,
} from "@/lib/agent-skill-sync-status";
import {
  type AgentSkill,
  deleteAgentSkill,
  listAgentSkills,
  pullAgentSkill,
  type SkillSyncStatus,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

const LIMIT = 20;

/**
 * How often the list re-fetches while any skill is still cloning. The clone
 * runs in the background on the server, so nothing pushes its result here.
 */
const POLL_INTERVAL_MS = 2000;

/** Status dot plus label, matching the workflow-task table's status treatment. */
function SyncStatus({ skill }: { skill: AgentSkill }) {
  const status = (skill.syncStatus ?? "pending") as SkillSyncStatus;
  const label = (
    <span className="flex items-center gap-2">
      <span
        className={`inline-block size-2 rounded-full ${SYNC_STATUS_DOT_CLASS[status]}`}
        aria-hidden
      />
      <span className="capitalize">{formatSyncStatusLabel(status)}</span>
    </span>
  );
  // The failure reason is the whole point of the failed state, but it is a raw
  // git/network message — too long for a cell, so it lives in the tooltip.
  return skill.syncError ? <Tooltip label={skill.syncError}>{label}</Tooltip> : label;
}

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
    header: "Status",
    sortField: "syncStatus",
    filterField: "syncStatus",
    noTruncate: true,
    cell: (s) => <SyncStatus skill={s} />,
  },
  {
    header: "Revision",
    sortField: "commitSha",
    className: "font-mono",
    cell: (s) => formatRevision(s.commitSha),
  },
  {
    header: "Created At",
    sortField: "createdAt",
    cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
  },
];

export default function AgentSkillsPage() {
  const canEdit = useHasRole(Role.DEVELOPER);
  const { rows, loading, error, offset, sort, filters, setOffset, setSort, setFilters, reload } =
    useTableQuery<AgentSkill>(listAgentSkills, {
      limit: LIMIT,
      errorMessage: "Failed to load agent skills",
    });
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [pullingId, setPullingId] = useState<string | null>(null);

  const anyPending = rows.some((s) => s.syncStatus === "pending");

  // A clone settles server-side with nothing to notify us, so poll until every
  // row has landed on ready or failed, then stop.
  useEffect(() => {
    if (!anyPending) return;
    const timer = setInterval(() => {
      void reload();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [anyPending, reload]);

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

  async function handlePull(id: string) {
    setPullingId(id);
    try {
      await pullAgentSkill(id);
      setActionError(null);
      await reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to pull agent skill");
    } finally {
      setPullingId(null);
    }
  }

  const columns: ColumnDef<AgentSkill>[] = [
    ...STATIC_COLUMNS,
    ...(canEdit
      ? [
          {
            header: "Actions",
            noTruncate: true,
            cell: (skill: AgentSkill) => (
              <div className="flex gap-2">
                <ActionIconButton
                  icon={RefreshCw}
                  label="Pull"
                  onClick={() => handlePull(skill.id)}
                  disabled={pullingId !== null || skill.syncStatus === "pending"}
                  spinning={pullingId === skill.id || skill.syncStatus === "pending"}
                />
                <DeleteIconButton onClick={() => handleDelete(skill.id, skill.name)} />
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Agent Skills" }]} />
      <AdminPageHeader
        title="Agent Skills"
        icon={Wand2}
        addHref={canEdit ? "/admin/agent-skills/new" : undefined}
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
