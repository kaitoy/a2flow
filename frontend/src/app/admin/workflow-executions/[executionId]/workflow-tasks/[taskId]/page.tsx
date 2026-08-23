/** @module WorkflowTaskDetailPage — Read-only admin detail page for a single WorkflowTask. */
"use client";

import { ListTodo, ListTree } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { StatusDot } from "@/components/ui/status-dot";
import {
  getWorkflowExecution,
  getWorkflowTask,
  isForbiddenError,
  listMcpServers,
  listWorkflowTasks,
  SUPPRESS_FORBIDDEN_TOAST,
  type WorkflowTask,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { formatStatusLabel, STATUS_DOT_CLASS } from "@/lib/workflow-task-status";

/** Upper bound used to fetch every sibling task, for resolving "Depends on" titles. */
const ALL_LIMIT = 1000;
/** Upper bound used to fetch the MCP server registry for tool-chip labels. */
const SERVER_LIMIT = 1000;

/**
 * Read-only detail page for a single `WorkflowTask`: its status, the
 * description and dependency/tool bindings copied in when the run started,
 * and any failure detail recorded against it.
 *
 * Nothing here is editable, for the same reason the task list page
 * (`workflow-tasks/page.tsx`) is read-only: a task is a copy of what the
 * workflow's published template said to run, advanced by the execution agent
 * and the approval flow — not an author-managed record — so a run's history
 * stays faithful to what actually ran.
 */
export default function WorkflowTaskDetailPage() {
  const { executionId, taskId } = useParams<{ executionId: string; taskId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [task, setTask] = useState<WorkflowTask | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The parent WorkflowExecution's workflow name, shown as a breadcrumb crumb
  // linking back to the session's own admin record.
  const [workflowName, setWorkflowName] = useState("");
  const [titleById, setTitleById] = useState<Map<string, string>>(new Map());
  const [serverNameById, setServerNameById] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let active = true;
    getWorkflowTask(taskId, SUPPRESS_FORBIDDEN_TOAST)
      .then((t) => {
        if (!active) return;
        setTask(t);
        setAudit({
          createdBy: t.createdBy,
          updatedBy: t.updatedBy,
          createdAt: t.createdAt,
          updatedAt: t.updatedAt,
        });
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [taskId]);

  useEffect(() => {
    getWorkflowExecution(executionId)
      .then((s) => setWorkflowName(s.name))
      .catch(() => {
        // Failure toast is shown globally by api.ts; the breadcrumb crumb
        // simply stays as an ellipsis.
      });
  }, [executionId]);

  // Only fetched when the loaded task actually has dependencies to resolve —
  // unlike the task list's graph, a single task's detail page has no use for
  // the full sibling set otherwise.
  useEffect(() => {
    if (!task || (task.dependsOnIds ?? []).length === 0) return;
    listWorkflowTasks(executionId, { limit: ALL_LIMIT })
      .then((tasks) => setTitleById(new Map(tasks.map((t) => [t.id, t.title]))))
      .catch(() => {
        // Dependency titles are cosmetic; chips fall back to a truncated id.
      });
  }, [executionId, task]);

  useEffect(() => {
    if (!task || (task.toolBindings ?? []).length === 0) return;
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNameById(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; tool chips fall back to truncated ids.
      });
  }, [task]);

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflow Executions", href: "/admin/workflow-executions" },
    { label: workflowName || "…", href: `/admin/workflow-executions/${executionId}` },
    {
      label: "Workflow Tasks",
      href: `/admin/workflow-executions/${executionId}/workflow-tasks`,
    },
    { label: task?.title || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !task) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={ListTodo} />}>
          <FormSkeleton fields={6} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  const status = task.status ?? "pending";
  const deps = task.dependsOnIds ?? [];
  const bindings = task.toolBindings ?? [];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={task.title}
            icon={ListTodo}
            secondaryAction={
              <HeaderIconButton
                label="View all tasks"
                onClick={() =>
                  router.push(`/admin/workflow-executions/${executionId}/workflow-tasks`)
                }
              >
                <ListTree size={18} strokeWidth={1.8} aria-hidden="true" />
              </HeaderIconButton>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label="Status"
              value={
                <StatusDot dotClass={STATUS_DOT_CLASS[status]} label={formatStatusLabel(status)} />
              }
            />
            <DetailItem label="Description" value={task.description || EMPTY_VALUE} />
            <DetailItem
              label="Depends on"
              value={
                deps.length === 0 ? (
                  EMPTY_VALUE
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {deps.map((id) => (
                      <Chip key={id} label={titleById.get(id) ?? `${id.slice(0, 8)}…`} />
                    ))}
                  </div>
                )
              }
            />
            <DetailItem
              label="Tools"
              value={
                bindings.length === 0 ? (
                  EMPTY_VALUE
                ) : (
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
                )
              }
            />
            <DetailItem
              label="Error Kind"
              value={
                task.errorKind ? (
                  <span className="capitalize">{task.errorKind.replace("_", " ")}</span>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem label="Error Message" value={task.errorMessage || EMPTY_VALUE} />
          </DetailList>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                router.push(`/admin/workflow-executions/${executionId}/workflow-tasks`)
              }
            >
              Back
            </Button>
          </div>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
