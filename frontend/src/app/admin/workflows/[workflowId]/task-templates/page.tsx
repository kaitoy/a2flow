/** @module WorkflowTaskTemplatesPage — Admin list page for a workflow's task templates. */
"use client";

import { ListTree, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { Chip } from "@/components/ui/chip";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { WorkflowTaskGraph } from "@/components/workflow-task-graph";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import {
  deleteWorkflowTaskTemplate,
  type FilterSpec,
  getWorkflow,
  listMcpServers,
  listWorkflowTaskTemplates,
  type SortSpec,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

/**
 * Upper bound (the backend maximum) used to fetch every template in one go.
 *
 * Both views want the whole set: the graph so dependency edges are not cut, and
 * the table so a hovered "Depends on" chip can name — and highlight — its target
 * row even when that row would have sat on another page.
 */
const ALL_LIMIT = 1000;
/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/** Which representation of the templates is currently shown. */
type View = "table" | "graph";

const VIEW_OPTIONS = [
  { value: "table" as const, label: "Table" },
  { value: "graph" as const, label: "Graph" },
];

function buildColumns(
  workflowId: string,
  titleById: Map<string, string>,
  serverNameById: Map<string, string>,
  onDelete: (id: string, title: string) => void,
  onHoverDependency: (id: string | null) => void,
  indexById: Map<string, number>,
  canEdit: boolean
): ColumnDef<WorkflowTaskTemplate>[] {
  const columns: ColumnDef<WorkflowTaskTemplate>[] = [
    {
      header: "#",
      className: "w-12 font-mono text-on-surface-variant",
      sortField: "createdAt",
      visibility: "always",
      cell: (t) => indexById.get(t.id) ?? 0,
    },
    {
      header: "Title",
      sortField: "title",
      filterField: "title",
      visibility: "always",
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
    ...auditColumns<WorkflowTaskTemplate>(),
  ];
  if (canEdit) {
    columns.push({
      header: "Actions",
      noTruncate: true,
      visibility: "always",
      cell: (t) => (
        <div className="flex justify-center gap-2">
          <DeleteIconButton onClick={() => onDelete(t.id, t.title)} />
        </div>
      ),
    });
  }
  return columns;
}

/**
 * Admin list of the task templates belonging to the workflow in the URL — the
 * workflow's reusable design, copied into every run at execute time. Templates
 * carry no status; the lifecycle belongs to the runs.
 *
 * Reads are open to any authenticated user (the backend allows any role to
 * list a workflow's templates), so a `requester` reaches this page read-only
 * via the workflow detail page's "View task templates" button: the "+ Add
 * task" button and the Actions column's Delete button — both of which hit
 * developer-only endpoints — render only for a `developer`.
 */
export default function WorkflowTaskTemplatesPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [templates, setTemplates] = useState<WorkflowTaskTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [sort, setSort] = useState<SortSpec | null>(null);
  const [filters, setFilters] = useState<FilterSpec[]>([]);
  const [view, setView] = useState<View>("table");
  // The template a hovered "Depends on" chip points at, called out in the table.
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; title: string } | null>(null);
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());
  // Only needed to name the parent workflow in the breadcrumb trail.
  const [workflowName, setWorkflowName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The graph needs every template in creation order, so it takes no sort or
      // filter at all; the table takes both but is likewise unpaginated.
      const data =
        view === "graph"
          ? await listWorkflowTaskTemplates(workflowId, { limit: ALL_LIMIT })
          : await listWorkflowTaskTemplates(workflowId, { limit: ALL_LIMIT, sort, filters });
      setTemplates(data);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    } finally {
      setLoading(false);
    }
  }, [workflowId, view, sort, filters]);

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
    getWorkflow(workflowId)
      .then((wf) => setWorkflowName(wf.name))
      .catch(() => {
        // The name only labels a breadcrumb; the crumb keeps its placeholder.
      });
  }, [workflowId]);

  function handleDelete(id: string, title: string) {
    setConfirmTarget({ id, title });
  }

  function handleOpenDesign() {
    // A design session has no id of its own — it is addressed by its workflow.
    router.push(`/workflows/${encodeURIComponent(workflowId)}/design-session`);
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

  const columns = buildColumns(
    workflowId,
    // Unpaginated, so every dependency resolves to a real title.
    new Map(templates.map((t) => [t.id, t.title])),
    serverNameById,
    handleDelete,
    setHighlightedId,
    new Map(templates.map((t, i) => [t.id, i + 1])),
    canEdit
  );
  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "taskTemplates",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: workflowName || "…", href: `/admin/workflows/${workflowId}` },
          { label: "Task Templates" },
        ]}
      />
      <AdminPageHeader
        title="Task Templates"
        icon={ListTree}
        addHref={canEdit ? `/admin/workflows/${workflowId}/task-templates/new` : undefined}
        addLabel="+ Add task"
        onRefresh={load}
        refreshing={loading}
        secondaryAction={
          canEdit ? (
            <HeaderIconButton label="Open design session" onClick={handleOpenDesign}>
              <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
            </HeaderIconButton>
          ) : undefined
        }
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
          aria-label="Template view"
        />
      </div>
      {view === "graph" ? (
        <WorkflowTaskGraph tasks={templates} serverNameById={serverNameById} />
      ) : (
        <DataTable
          columns={visibleColumns}
          rows={templates}
          loading={loading}
          emptyMessage="No task templates for this workflow yet."
          emptyIcon={ListTree}
          getRowKey={(t) => t.id}
          sort={sort}
          onSortChange={setSort}
          filters={filters}
          onFilterChange={setFilters}
          highlightedRowKey={highlightedId}
        />
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
