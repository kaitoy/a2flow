/** @module AgentSkillsPage — Admin list page for managing agent skills. */
"use client";

import { RefreshCw, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { GenerateWorkflowDialog } from "@/components/admin/generate-workflow-dialog";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tagsColumn } from "@/components/admin/tag-columns";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { StatusDot } from "@/components/ui/status-dot";
import { Tooltip } from "@/components/ui/tooltip";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTenantNames, useUserNames } from "@/hooks/useNames";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTags } from "@/hooks/useTags";
import { useT } from "@/i18n/provider";
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
    <StatusDot dotClass={SYNC_STATUS_DOT_CLASS[status]} label={formatSyncStatusLabel(status)} />
  );
  // The failure reason is the whole point of the failed state, but it is a raw
  // git/network message — too long for a cell, so it lives in the tooltip. The
  // trigger has to be a DOM element: Tooltip clones its child to attach a ref
  // and mouse handlers, which a component would silently drop.
  return skill.syncError ? (
    <Tooltip label={skill.syncError}>
      <span className="inline-flex">{label}</span>
    </Tooltip>
  ) : (
    label
  );
}

function buildColumns(
  names: Map<string, string>,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<AgentSkill>[] {
  return [
    ...(isAllTenantsView ? [tenantColumn<AgentSkill>(tenantNames)] : []),
    idColumn<AgentSkill>(),
    {
      header: "common.name" as const,
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (s) => (
        <Link
          href={`/agent-skills/${s.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {s.name}
        </Link>
      ),
    },
    {
      header: "common.description" as const,
      cell: (s) => s.description || "—",
    },
    {
      header: "common.repoUrl" as const,
      sortField: "repoUrl",
      filterField: "repoUrl",
      className: "font-mono",
      cell: (s) => s.repoUrl,
    },
    {
      header: "common.repoPath" as const,
      sortField: "repoPath",
      filterField: "repoPath",
      className: "font-mono",
      visibility: "optional",
      cell: (s) => s.repoPath || "—",
    },
    {
      header: "common.ref" as const,
      sortField: "repoRef",
      filterField: "repoRef",
      className: "font-mono",
      visibility: "optional",
      cell: (s) => s.repoRef || "—",
    },
    {
      header: "common.status" as const,
      sortField: "syncStatus",
      filterField: "syncStatus",
      noTruncate: true,
      cell: (s) => <SyncStatus skill={s} />,
    },
    {
      header: "agentSkills.revision" as const,
      sortField: "commitSha",
      className: "font-mono",
      visibility: "optional",
      cell: (s) => formatRevision(s.commitSha),
    },
    {
      header: "common.createdAt" as const,
      sortField: "createdAt",
      visibility: "optional",
      cell: (s) => <DateTime value={s.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "common.authUsername" as const,
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.repoAuthUsername || "—",
    },
    {
      header: "common.authPassword" as const,
      visibility: "optional",
      className: "font-mono",
      cell: (s) => s.repoAuthPassword || "—",
    },
    {
      header: "agentSkills.syncedAt" as const,
      visibility: "optional",
      cell: (s) =>
        s.syncedAt ? <DateTime value={s.syncedAt} className="text-on-surface-variant" /> : "—",
    },
    ...auditColumns<AgentSkill>(names),
  ];
}

export default function AgentSkillsPage() {
  const t = useT();
  const canEdit = useHasRole(Role.DEVELOPER);
  const {
    rows,
    loading,
    refreshing,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    tagIds,
    setTagIds,
    reload,
  } = useTableQuery<AgentSkill>(listAgentSkills, { limit: LIMIT });
  const { byId: tagsById } = useTags();
  const names = useUserNames(rows.flatMap((s) => [s.createdBy, s.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((s) => s.tenantId) : []);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [generateTarget, setGenerateTarget] = useState<{ id: string; name: string } | null>(null);
  const [pullingId, setPullingId] = useState<string | null>(null);

  const anyPending = rows.some((s) => s.syncStatus === "pending");

  // A clone settles server-side with nothing to notify us, so poll until every
  // row has landed on ready or failed, then stop. Silently: the table stays on
  // screen and only the cells that changed re-render, so a clone that takes a
  // minute does not strobe the whole page.
  useEffect(() => {
    if (!anyPending) return;
    const timer = setInterval(() => {
      void reload({ silent: true });
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
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  async function handlePull(id: string) {
    setPullingId(id);
    try {
      await pullAgentSkill(id);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setPullingId(null);
    }
  }

  const columns: ColumnDef<AgentSkill>[] = [
    ...buildColumns(names, tenantNames, isAllTenantsView),
    tagsColumn<AgentSkill>((row) => row.tagIds, tagsById),
    ...(canEdit
      ? [
          {
            header: "common.actions" as const,
            noTruncate: true,
            visibility: "always" as const,
            cell: (skill: AgentSkill) => (
              <div className="flex justify-center gap-2">
                <ActionIconButton
                  icon={Sparkles}
                  label={t("agentSkills.generateWorkflow")}
                  onClick={() => setGenerateTarget({ id: skill.id, name: skill.name })}
                  // A skill can only back a design run once its clone has
                  // published a revision.
                  disabled={skill.syncStatus !== "ready"}
                />
                <ActionIconButton
                  icon={RefreshCw}
                  label={t("agentSkills.pull")}
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

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "agentSkills",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[{ label: t("common.home"), href: "/" }, { label: t("common.agentSkills") }]}
      />
      <AdminPageHeader
        title={t("common.agentSkills")}
        icon={Wand2}
        addHref={canEdit ? "/agent-skills/new" : undefined}
        addLabel={t("agentSkills.addSkill")}
        onRefresh={reload}
        refreshing={loading || refreshing}
        columnPicker={
          <ColumnPicker
            options={options}
            value={selected}
            onChange={setSelected}
            onReset={reset}
            customized={customized}
          />
        }
      />
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage={t("agentSkills.noAgentSkillsRegisteredYet")}
        emptyIcon={Wand2}
        getRowKey={(skill) => skill.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
        tagIds={tagIds}
        onTagIdsChange={setTagIds}
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
        title={t("agentSkills.deleteAgentSkill")}
        description={confirmTarget ? t("common.deleteName", { name: confirmTarget.name }) : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
      <GenerateWorkflowDialog
        open={generateTarget !== null}
        skillId={generateTarget?.id ?? ""}
        defaultName={generateTarget?.name ?? ""}
        onClose={() => setGenerateTarget(null)}
      />
    </AdminPageContainer>
  );
}
