/** @module WorkflowTasksPage — Read-only admin view of a WorkflowSession's tasks. */
"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { WorkflowTaskGraph } from "@/components/workflow-task-graph";
import {
  type FilterSpec,
  listMcpServers,
  listWorkflowTasks,
  type SortSpec,
  type WorkflowTask,
  type WorkflowTaskStatus,
} from "@/lib/api";
import {
  formatStatusLabel,
  STATUS_DOT_CLASS,
  WORKFLOW_TASK_STATUSES,
} from "@/lib/workflow-task-status";

/** Page size for the paginated table view. */
const LIMIT = 20;
/** Upper bound (backend maximum) used to fetch the whole DAG for the graph view. */
const GRAPH_LIMIT = 1000;
/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/** Which representation of the tasks is currently shown. */
type View = "table" | "graph";

const VIEW_OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

/** Small colored dot shown next to the status label for quick visual scanning. */
function StatusDot({ status }: { status: WorkflowTaskStatus }) {
  return (
    <span className={`inline-block size-2 rounded-full ${STATUS_DOT_CLASS[status]}`} aria-hidden />
  );
}

/** Pill showing a single related item (dependency or bound tool) by label, in the mono data face. */
function Chip({ label }: { label: string }) {
  return (
    <span className="inline-block rounded-full glass-panel px-2 py-0.5 font-mono text-xs text-on-surface-variant">
      {label}
    </span>
  );
}

function buildColumns(
  titleById: Map<string, string>,
  serverNameById: Map<string, string>
): ColumnDef<WorkflowTask>[] {
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
      cell: (t) => <span className="font-medium text-on-surface">{t.title}</span>,
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
      header: "Status",
      noTruncate: true,
      sortField: "status",
      filterField: "status",
      filterOp: "eq",
      filterOptions: WORKFLOW_TASK_STATUSES.map((s) => ({
        label: formatStatusLabel(s),
        value: s,
      })),
      cell: (t) => {
        const status = t.status ?? "pending";
        return (
          <div className="flex items-center gap-2">
            <StatusDot status={status} />
            <span className="capitalize">{formatStatusLabel(status)}</span>
          </div>
        );
      },
    },
  ];
}

/**
 * Read-only admin list of a WorkflowSession's tasks. The tasks are copies of
 * the workflow's published templates, advanced by the execution agent (and
 * the approval flow) — the plan itself is edited on the workflow's task
 * templates, not here, so a run's history stays faithful to what actually ran.
 */
export default function WorkflowTasksPage() {
  const { wsId } = useParams<{ wsId: string }>();
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<SortSpec | null>(null);
  const [filters, setFilters] = useState<FilterSpec[]>([]);
  const [view, setView] = useState<View>("table");
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The graph needs every task (in position order) so dependency edges are
      // not cut across pages or hidden by sort/filter.
      const data =
        view === "graph"
          ? await listWorkflowTasks(wsId, { limit: GRAPH_LIMIT })
          : await listWorkflowTasks(wsId, { limit: LIMIT, offset, sort, filters });
      setTasks(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflow tasks");
    } finally {
      setLoading(false);
    }
  }, [wsId, offset, view, sort, filters]);

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

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          { label: "Workflow Tasks" },
        ]}
      />
      <AdminPageHeader
        title="Workflow Tasks"
        icon={ListTree}
        onRefresh={load}
        refreshing={loading}
      />
      <div className="mb-4">
        <SegmentedControl
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="Task view"
        />
      </div>
      <div className="mb-4">
        <ErrorBanner error={error} />
      </div>
      {view === "graph" ? (
        <WorkflowTaskGraph tasks={tasks} />
      ) : (
        <>
          <DataTable
            columns={buildColumns(new Map(tasks.map((t) => [t.id, t.title])), serverNameById)}
            rows={tasks}
            loading={loading}
            emptyMessage="No tasks for this session yet."
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
            count={tasks.length}
            onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
            onNext={() => setOffset((o) => o + LIMIT)}
          />
        </>
      )}
    </AdminPageContainer>
  );
}
