/** @module WorkflowTasksPage — Read-only admin view of a WorkflowSession's tasks. */
"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { Chip } from "@/components/ui/chip";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { WorkflowTaskGraph } from "@/components/workflow-task-graph";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import {
  type FilterSpec,
  getWorkflowSession,
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

/**
 * Upper bound (the backend maximum) used to fetch every task in one go.
 *
 * Both views want the whole set: the graph so dependency edges are not cut, and
 * the table so a hovered "Depends on" chip can name — and highlight — its target
 * row even when that row would have sat on another page.
 */
const ALL_LIMIT = 1000;
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

function buildColumns(
  titleById: Map<string, string>,
  serverNameById: Map<string, string>,
  onHoverDependency: (id: string | null) => void
): ColumnDef<WorkflowTask>[] {
  return [
    {
      header: "#",
      className: "w-12 font-mono text-on-surface-variant",
      sortField: "position",
      visibility: "always",
      cell: (t) => t.position ?? 0,
    },
    {
      header: "Title",
      sortField: "title",
      filterField: "title",
      visibility: "always",
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
              <Chip
                key={id}
                label={titleById.get(id) ?? `${id.slice(0, 8)}…`}
                onMouseEnter={() => onHoverDependency(id)}
                onMouseLeave={() => onHoverDependency(null)}
              />
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
 * the approval flow) — the task templates themselves are edited on the workflow's task
 * templates, not here, so a run's history stays faithful to what actually ran.
 */
export default function WorkflowTasksPage() {
  const { wsId } = useParams<{ wsId: string }>();
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<SortSpec | null>(null);
  const [filters, setFilters] = useState<FilterSpec[]>([]);
  const [view, setView] = useState<View>("table");
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  // The task a hovered "Depends on" chip points at, called out in the table.
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  // The parent WorkflowSession's workflow name, shown as a breadcrumb crumb
  // linking back to the session's own admin record.
  const [workflowName, setWorkflowName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The graph needs every task in position order, so it takes no sort or
      // filter at all; the table takes both but is likewise unpaginated.
      const data =
        view === "graph"
          ? await listWorkflowTasks(wsId, { limit: ALL_LIMIT })
          : await listWorkflowTasks(wsId, { limit: ALL_LIMIT, sort, filters });
      setTasks(data);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }, [wsId, view, sort, filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, []);

  useEffect(() => {
    getWorkflowSession(wsId)
      .then((s) => setWorkflowName(s.workflowName))
      .catch(() => {
        // Failure toast is shown globally by api.ts; the breadcrumb crumb
        // simply stays as an ellipsis.
      });
  }, [wsId]);

  const columns = buildColumns(
    // Unpaginated, so every dependency resolves to a real title.
    new Map(tasks.map((t) => [t.id, t.title])),
    serverNameById,
    setHighlightedId
  );
  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "workflowTasks",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          // Links back to this run's own admin record; an ellipsis stands in
          // until its workflow name has loaded.
          { label: workflowName || "…", href: `/admin/workflow-sessions/${wsId}` },
          { label: "Workflow Tasks" },
        ]}
      />
      <AdminPageHeader
        title="Workflow Tasks"
        icon={ListTree}
        onRefresh={load}
        refreshing={loading}
        columnPicker={
          // The graph view has no columns to choose from.
          view === "table" ? (
            <ColumnPicker
              options={options}
              value={selected}
              onChange={setSelected}
              onReset={reset}
              customized={customized}
            />
          ) : undefined
        }
      />
      <div className="mb-4">
        <SegmentedControl
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="Task view"
        />
      </div>
      {view === "graph" ? (
        <WorkflowTaskGraph tasks={tasks} serverNameById={serverNameById} />
      ) : (
        <DataTable
          columns={visibleColumns}
          rows={tasks}
          loading={loading}
          emptyMessage="No tasks for this session yet."
          emptyIcon={ListTree}
          getRowKey={(t) => t.id}
          sort={sort}
          onSortChange={setSort}
          filters={filters}
          onFilterChange={setFilters}
          highlightedRowKey={highlightedId}
        />
      )}
    </AdminPageContainer>
  );
}
