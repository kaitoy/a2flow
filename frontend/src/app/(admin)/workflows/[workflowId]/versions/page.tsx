/** @module WorkflowVersionsPage — Admin list of the versions a workflow was published as. */
"use client";

import { History, RotateCcw } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useUserNames } from "@/hooks/useNames";
import {
  type FilterSpec,
  getWorkflow,
  listWorkflowVersions,
  restoreWorkflowVersion,
  type SortSpec,
  type WorkflowVersion,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Upper bound (the backend maximum): a workflow's history is shown unpaginated. */
const ALL_LIMIT = 1000;

function buildColumns(
  names: Map<string, string>,
  onRestore: (version: WorkflowVersion) => void,
  canRestore: boolean,
  canViewPrompt: boolean
): ColumnDef<WorkflowVersion>[] {
  const columns: ColumnDef<WorkflowVersion>[] = [
    idColumn<WorkflowVersion>(),
    {
      header: "Version",
      className: "w-24 font-mono",
      sortField: "version",
      visibility: "always",
      cell: (v) => `v${v.version}`,
    },
    {
      header: "Name",
      sortField: "name",
      filterField: "name",
      visibility: "always",
      cell: (v) => v.name,
    },
    {
      header: "Description",
      sortField: "description",
      filterField: "description",
      cell: (v) => v.description || "—",
    },
    // The backend blanks prompts for anyone else, so the column would be empty.
    ...(canViewPrompt
      ? [
          {
            header: "Prompt",
            sortField: "prompt",
            filterField: "prompt",
            visibility: "optional" as const,
            cell: (v: WorkflowVersion) => v.prompt || "—",
          },
        ]
      : []),
    ...auditColumns<WorkflowVersion>(names),
  ];
  if (canRestore) {
    columns.push({
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (v) => (
        <div className="flex justify-center gap-2">
          <ActionIconButton icon={RotateCcw} label="Restore" onClick={() => onRestore(v)} />
        </div>
      ),
    });
  }
  return columns;
}

/**
 * Admin list of every version the workflow in the URL was published as, newest
 * first. Only an `admin`, `developer`, or `reviewer` may browse it (the backend
 * refuses a `requester` or `approver`, and the detail page hides its link from
 * them); a `developer` additionally
 * gets a Restore action per row, which writes that version's design back into
 * the workflow without publishing it, then returns to the workflow's page.
 */
export default function WorkflowVersionsPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canRestore = useHasRole(Role.DEVELOPER);
  const canViewPrompt = useHasRole(Role.ADMIN, Role.DEVELOPER, Role.REVIEWER);
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<SortSpec | null>(null);
  const [filters, setFilters] = useState<FilterSpec[]>([]);
  const [confirmTarget, setConfirmTarget] = useState<WorkflowVersion | null>(null);
  // Only needed to name the parent workflow in the breadcrumb trail.
  const [workflowName, setWorkflowName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setVersions(await listWorkflowVersions(workflowId, { limit: ALL_LIMIT, sort, filters }));
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }, [workflowId, sort, filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    getWorkflow(workflowId)
      .then((wf) => setWorkflowName(wf.name))
      .catch(() => {
        // The name only labels a breadcrumb; the crumb keeps its placeholder.
      });
  }, [workflowId]);

  async function executeRestore() {
    if (!confirmTarget) return;
    const { version } = confirmTarget;
    setConfirmTarget(null);
    try {
      await restoreWorkflowVersion(workflowId, version);
      dispatch(showToast({ message: `Version ${version} restored` }));
      router.push(`/workflows/${workflowId}`);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const names = useUserNames(versions.flatMap((v) => [v.createdBy, v.updatedBy]));
  const columns = buildColumns(names, setConfirmTarget, canRestore, canViewPrompt);

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflowVersions",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Workflows", href: "/workflows" },
          { label: workflowName || "…", href: `/workflows/${workflowId}` },
          { label: "Versions" },
        ]}
      />
      <AdminPageHeader
        title="Version History"
        icon={History}
        onRefresh={load}
        refreshing={loading}
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
        rows={versions}
        loading={loading}
        emptyMessage="This workflow has not been published yet."
        emptyIcon={History}
        getRowKey={(v) => v.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
      />
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Restore Version"
        description={
          confirmTarget
            ? `Replace the workflow's current design with version ${confirmTarget.version}? It is not published until you publish it again.`
            : ""
        }
        confirmLabel="Restore"
        onConfirm={executeRestore}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
