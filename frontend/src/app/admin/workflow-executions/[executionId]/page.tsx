/** @module WorkflowExecutionDetailPage — Read-only admin detail page for an executed WorkflowExecution. */
"use client";

import { ClipboardList, ListChecks, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { WorkflowExecutionStatusLabel } from "@/components/admin/workflow-execution-status";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import {
  deleteWorkflowExecution,
  getUserNames,
  getWorkflowExecution,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  type WorkflowExecution,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/**
 * Read-only detail page for a single executed `WorkflowExecution`: the workflow
 * and agent skill it ran, who ran it, and when — followed by the same audit
 * footer every admin detail page shows.
 *
 * Nothing here is editable: a session is a record of a run, not an
 * author-managed entity. The header offers quick jumps to the session's task
 * list and its live chat, mirroring the icon actions already on the
 * `workflow-executions` list page. Delete is offered for the same reason the
 * list page offers it there.
 */
export default function WorkflowExecutionDetailPage() {
  const { executionId } = useParams<{ executionId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [session, setSession] = useState<WorkflowExecution | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    let active = true;
    getWorkflowExecution(executionId, SUPPRESS_FORBIDDEN_TOAST)
      .then(async (s) => {
        if (!active) return;
        setSession(s);
        setAudit({
          createdBy: s.createdBy,
          updatedBy: s.updatedBy,
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
        });
        const names = await getUserNames([s.initiatorId]);
        if (active) setUserName(names.get(s.initiatorId) ?? null);
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
  }, [executionId]);

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflowExecution(executionId);
      router.push("/admin/workflow-executions");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflow Executions", href: "/admin/workflow-executions" },
    { label: session?.name || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !session) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={ListChecks} />}>
          <FormSkeleton fields={6} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={session.name}
            icon={ListChecks}
            secondaryAction={
              <>
                <HeaderIconButton
                  label="View tasks"
                  onClick={() =>
                    router.push(`/admin/workflow-executions/${executionId}/workflow-tasks`)
                  }
                >
                  <ClipboardList size={18} strokeWidth={1.8} aria-hidden="true" />
                </HeaderIconButton>
                <HeaderIconButton
                  label="Open workflow session"
                  onClick={() => router.push(`/workflow-executions/${executionId}/session`)}
                >
                  <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
                </HeaderIconButton>
              </>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem
              label="Name"
              value={
                session.workflowId ? (
                  <Link
                    href={`/admin/workflows/${session.workflowId}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {session.name}
                  </Link>
                ) : (
                  session.name
                )
              }
            />
            <DetailItem
              label="Status"
              value={<WorkflowExecutionStatusLabel status={session.status} />}
            />
            <DetailItem label="Description" value={session.description || EMPTY_VALUE} />
            <DetailItem
              label="Agent Skill"
              value={
                <Link
                  href={`/admin/agent-skills/${session.agentSkillId}`}
                  className="font-medium text-accent transition-colors hover:underline"
                >
                  {session.agentSkillName}
                </Link>
              }
            />
            <DetailItem
              label="Repository"
              value={
                <a
                  href={session.agentSkillRepoUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="break-all text-accent transition-colors hover:underline"
                >
                  {session.agentSkillRepoUrl}
                </a>
              }
            />
            <DetailItem label="Repository Path" value={session.agentSkillRepoPath || EMPTY_VALUE} />
            <DetailItem
              label="Commit"
              value={
                <span className="font-mono text-xs">
                  {session.agentSkillCommitSha ?? EMPTY_VALUE}
                </span>
              }
            />
            <DetailItem
              label="Initiator"
              value={
                <Link
                  href={`/admin/users/${session.initiatorId}`}
                  className="font-medium text-accent transition-colors hover:underline"
                >
                  {userName ?? session.initiatorId}
                </Link>
              }
            />
            <DetailItem
              label="Session ID"
              value={<span className="font-mono text-xs">{session.sessionId}</span>}
            />
          </DetailList>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/admin/workflow-executions")}
            >
              Back
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={() => setConfirmOpen(true)}
              className="ml-auto"
            >
              Delete
            </Button>
          </div>
        </div>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Workflow Execution"
        description={`Delete "${session.name}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
