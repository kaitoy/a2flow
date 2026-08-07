/** @module WorkflowSessionDetailPage — Read-only admin detail page for an executed WorkflowSession. */
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
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import {
  deleteWorkflowSession,
  getUserNames,
  getWorkflowSession,
  type WorkflowSession,
} from "@/lib/api";

/** Placeholder shown in place of an attribute that has no value. */
const EMPTY = "—";

/**
 * Read-only detail page for a single executed `WorkflowSession`: the workflow
 * and agent skill it ran, who ran it, and when — followed by the same audit
 * footer every admin detail page shows.
 *
 * Nothing here is editable: a session is a record of a run, not an
 * author-managed entity. The header offers quick jumps to the session's task
 * list and its live chat, mirroring the icon actions already on the
 * `workflow-sessions` list page. Delete is offered for the same reason the
 * list page offers it there.
 */
export default function WorkflowSessionDetailPage() {
  const { wsId } = useParams<{ wsId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<WorkflowSession | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    let active = true;
    getWorkflowSession(wsId)
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
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [wsId]);

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflowSession(wsId);
      router.push("/admin/workflow-sessions");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
    { label: session?.workflowName || "…" },
  ];

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
            title={session.workflowName}
            icon={ListChecks}
            secondaryAction={
              <>
                <HeaderIconButton
                  label="View tasks"
                  onClick={() => router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`)}
                >
                  <ClipboardList size={18} strokeWidth={1.8} aria-hidden="true" />
                </HeaderIconButton>
                <HeaderIconButton
                  label="Open workflow session"
                  onClick={() => router.push(`/workflow-sessions/${wsId}`)}
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
          <DetailList>
            <DetailItem
              label="Workflow"
              value={
                session.workflowId ? (
                  <Link
                    href={`/admin/workflows/${session.workflowId}`}
                    className="font-medium text-accent transition-colors hover:underline"
                  >
                    {session.workflowName}
                  </Link>
                ) : (
                  session.workflowName
                )
              }
            />
            <DetailItem label="Description" value={session.workflowDescription || EMPTY} />
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
            <DetailItem label="Repository Path" value={session.agentSkillRepoPath || EMPTY} />
            <DetailItem
              label="Commit"
              value={
                <span className="font-mono text-xs">{session.agentSkillCommitSha ?? EMPTY}</span>
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
              onClick={() => router.push("/admin/workflow-sessions")}
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
        title="Delete Workflow Session"
        description={`Delete "${session.workflowName}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
