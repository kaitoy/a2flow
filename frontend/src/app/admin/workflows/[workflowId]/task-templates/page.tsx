/** @module WorkflowTaskTemplatesPage — Admin list page for a workflow's task templates. */
"use client";

import { ListTree } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { WorkflowTaskGraph } from "@/components/workflow-task-graph";
import {
  deleteWorkflowTaskTemplate,
  type FilterSpec,
  listMcpServers,
  listWorkflowTaskTemplates,
  type SortSpec,
  type WorkflowTaskTemplate,
} from "@/lib/api";

/** Page size for the paginated table view. */
const LIMIT = 20;
/** Upper bound (backend maximum) used to fetch the whole DAG for the graph view. */
const GRAPH_LIMIT = 1000;
/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/** Which representation of the templates is currently shown. */
type View = "table" | "graph";

const VIEW_OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

/** Pill showing a single related item (dependency or bound tool) by label, in the mono data face. */
function Chip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-full glass-panel px-2 py-0.5 font-mono text-xs text-on-surface-variant">
      {label}
    </span>
  );
}

function buildColumns(
  workflowId: string,
  titleById: Map<string, string>,
  serverNameById: Map<string, string>,
  onDelete: (id: string, title: string) => void
): ColumnDef<WorkflowTaskTemplate>[] {
  return [
    {
      header: "#",
      className: "w-12 font-mono text-on-surface-variant",
      sortField: "position",
      cell: (t) => t.position ?? 0,
    },
    {
      header: "Title",
      sortField: "title",
      filterField: "title",
      cell: (t) => (
        <Link
          href={`/admin/workflows/${workflowId}/task-templates/${t.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {t.title}
        </Link>
      ),
    },
    {
      header: "Description",
      sortField: "description",
      filterField: "description",
      cell: (t) => t.description || "—",
    },
    {
      // Resolved from the dependency join table; not a real column.
      header: "Depends on",
      noTruncate: true,
      cell: (t) => {
        const deps = t.dependsOnIds ?? [];
        if (deps.length === 0) return <span className="text-on-surface-variant">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {deps.map((id) => (
              <Chip key={id} label={titleById.get(id) ?? `${id.slice(0, 8)}…`} />
            ))}
          </div>
        );
      },
    },
    {
      // Resolved from the tool-binding join table; not a real column.
      header: "Tools",
      noTruncate: true,
      cell: (t) => {
        const bindings = t.toolBindings ?? [];
        if (bindings.length === 0) return <span className="text-on-surface-variant">—</span>;
        return (
          <div className="flex flex-wrap gap-1">
            {bindings.map((b) => (
              <Chip
                key={`${b.mcpServerId}:${b.toolName}`}
                label={`${
                  serverNameById.get(b.mcpServerId) ?? `${b.mcpServerId.slice(0, 8)}…`
                }: ${b.toolName}`}
              />
            ))}
          </div>
        );
      },
    },
    {
      header: "Actions",
      noTruncate: true,
      cell: (t) => (
        <div className="flex gap-2">
          <DeleteIconButton onClick={() => onDelete(t.id, t.title)} />
        </div>
      ),
    },
  ];
}

/**
 * Admin list of the task templates belonging to the workflow in the URL — the
 * workflow's reusable plan, copied into every run at execute time. Templates
 * carry no status; the lifecycle belongs to the runs.
 */
export default function WorkflowTaskTemplatesPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const [templates, setTemplates] = useState<WorkflowTaskTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<SortSpec | null>(null);
  const [filters, setFilters] = useState<FilterSpec[]>([]);
  const [view, setView] = useState<View>("table");
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; title: string } | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The graph needs every template (in position order) so dependency edges
      // are not cut across pages or hidden by sort/filter.
      const data =
        view === "graph"
          ? await listWorkflowTaskTemplates(workflowId, { limit: GRAPH_LIMIT })
          : await listWorkflowTaskTemplates(workflowId, { limit: LIMIT, offset, sort, filters });
      setTemplates(data);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }, [workflowId, offset, view, sort, filters]);

  useEffect(() => {
    load();
  }, [load]);

  /** Set the sort directive and return to the first page. */
  function handleSortChange(next: SortSpec | null) {
    setSort(next);
    setOffset(0);
  }

  /** Set the filter directives and return to the first page. */
  function handleFilterChange(next: FilterSpec[]) {
    setFilters(next);
    setOffset(0);
  }

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, []);

  function handleDelete(id: string, title: string) {
    setConfirmTarget({ id, title });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteWorkflowTaskTemplate(confirmTarget.id);
      setConfirmTarget(null);
      await load();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "Edit", href: `/admin/workflows/${workflowId}` },
          { label: "Task Templates" },
        ]}
      />
      <AdminPageHeader
        title="Task Templates"
        icon={ListTree}
        addHref={`/admin/workflows/${workflowId}/task-templates/new`}
        addLabel="+ Add template"
        onRefresh={load}
        refreshing={loading}
      />
      <div className="mb-4">
        <SegmentedControl
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="Template view"
        />
      </div>
      {view === "graph" ? (
        <WorkflowTaskGraph tasks={templates} />
      ) : (
        <>
          <DataTable
            columns={buildColumns(
              workflowId,
              new Map(templates.map((t) => [t.id, t.title])),
              serverNameById,
              handleDelete
            )}
            rows={templates}
            loading={loading}
            emptyMessage="No task templates for this workflow yet."
            emptyIcon={ListTree}
            getRowKey={(t) => t.id}
            sort={sort}
            onSortChange={handleSortChange}
            filters={filters}
            onFilterChange={handleFilterChange}
          />
          <PaginationControls
            offset={offset}
            limit={LIMIT}
            count={templates.length}
            onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
            onNext={() => setOffset((o) => o + LIMIT)}
          />
        </>
      )}
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete Task Template"
        description={confirmTarget ? `Delete "${confirmTarget.title}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </AdminPageContainer>
  );
}
