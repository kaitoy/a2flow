/** @module WorkflowDetailPage — Admin detail page for an existing workflow and its task templates. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  ClipboardList,
  GitCompare,
  Loader2,
  MessageSquareText,
  Play,
  PowerOff,
  Rocket,
  Sparkles,
  Undo2,
  Workflow as WorkflowIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DescriptionDiffDialog } from "@/components/admin/description-diff-dialog";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { RunWorkflowDialog } from "@/components/admin/run-workflow-dialog";
import { StatusCard } from "@/components/admin/status-card";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { StatusDot } from "@/components/ui/status-dot";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import {
  type AgentSkill,
  deactivateWorkflow,
  deleteWorkflow,
  discardWorkflowChanges,
  executeWorkflow,
  generateWorkflowDescription,
  getAgentSkill,
  getWorkflow,
  isForbiddenError,
  publishWorkflow,
  SUPPRESS_FORBIDDEN_TOAST,
  setWorkflowTags,
  updateWorkflow,
  type Workflow,
  type WorkflowStatus,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { Role, useHasRole } from "@/lib/roles";
import {
  canExecuteWorkflow,
  formatWorkflowStatusLabel,
  WORKFLOW_STATUS_DOT_CLASS,
} from "@/lib/workflow-status";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How often (ms) to re-fetch the workflow while its task templates are still generating. */
const POLL_INTERVAL_MS = 2000;

// name and description are client-writable by any developer; reuse the
// generated name constraint and allow a free-form (bounded) description.
// generatedDescription is only ever submitted for a super_admin caller (see
// isSuperAdmin below), but stays part of the schema so register()/reset() can
// address it regardless of role.
const schema = z.object({
  name: zGenerateWorkflowRequest.shape.name,
  description: z.string().max(2000),
  generatedDescription: z.string().max(2000),
});

type FormValues = z.infer<typeof schema>;

/** Status dot plus label for the workflow's lifecycle state. */
function StatusLine({ workflow }: { workflow: Workflow }) {
  const status = (workflow.status ?? "draft") as WorkflowStatus;
  return (
    <StatusDot
      dotClass={WORKFLOW_STATUS_DOT_CLASS[status]}
      label={formatWorkflowStatusLabel(status)}
    />
  );
}

/**
 * Detail page of a generated workflow, titled with the workflow's own name:
 * edit name/description, watch the design run settle, open the design
 * session to adjust the task templates by chat, run the workflow, manage the task
 * templates, and publish the workflow to make it executable.
 *
 * The header's Run button follows the same `canExecuteWorkflow` rule as the
 * workflows list — hidden for viewers who can't execute workflows at all, and
 * disabled for a `draft` workflow unless the viewer can also edit workflows
 * (pre-publish testing) — and, on success, navigates to the new run's
 * `WorkflowExecution` page just like the list's Run action.
 *
 * `description` is a free-form field any developer can set; the workflow
 * session falls back to the AI-generated `generatedDescription` whenever it's
 * empty. `generatedDescription` itself is read-only for everyone except a
 * super admin, who can edit it directly to correct the AI's summary. Any
 * developer can instead re-derive it from the design conversation through
 * the field's own generate button, which saves the new summary server-side
 * right away (and so moves a published workflow to `modified`). Since the
 * override is usually a hand-edit of that summary, the Description field also
 * carries a button opening a word-level diff of the two current (possibly
 * unsaved) values.
 *
 * Editing a published workflow moves it to `modified` — runs keep using the
 * last published version — so the status bar then also offers "Discard
 * changes", which restores that version and returns the workflow to
 * `published`. A `published`/`modified` workflow can also be "Deactivated"
 * back to `draft`, revoking `requester` execute access until it is published
 * again.
 *
 * A viewer without the developer role (e.g. `requester`, who can only reach
 * this page to check on or run a workflow) gets a read-only rendering: Name
 * and Description show as plain text, and every action that would hit a
 * developer-only endpoint — Open design session, Discard changes, Deactivate,
 * Publish, Save, Delete — is hidden rather than left to fail with a 403 on
 * click. Task templates stay reachable read-only for such a viewer too — the
 * header button is labeled "View task templates" instead of "Manage task
 * templates" and the templates screens it opens hide their own write actions
 * the same way. The "Workflow status" bar itself stays visible for such a
 * viewer — the status is useful context regardless of role — but its
 * developer-only actions (Discard changes, Deactivate, Publish) are hidden
 * individually the same way as elsewhere on the page.
 */
export default function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  const canRun = useHasRole(Role.REQUESTER, Role.DEVELOPER);
  const canEdit = useHasRole(Role.DEVELOPER);
  const canViewTemplates = useHasRole(Role.REQUESTER, Role.DEVELOPER);
  const isAllTenantsView = useIsAllTenantsView();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [skill, setSkill] = useState<AgentSkill | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false);
  const [confirmDeactivateOpen, setConfirmDeactivateOpen] = useState(false);
  const [confirmPublishOpen, setConfirmPublishOpen] = useState(false);
  const [confirmRunOpen, setConfirmRunOpen] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  // Tags live outside the form state and outside `applyWorkflow`: that runs on
  // every generation poll too, and re-applying the server's tags mid-edit would
  // discard the user's in-progress selection.
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const publish = useAsyncAction({ showDone: false });
  const discard = useAsyncAction({ showDone: false });
  const deactivate = useAsyncAction({ showDone: false });
  const run = useAsyncAction({ showDone: false });
  const generateDescription = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", description: "", generatedDescription: "" },
  });

  // Subscribed rather than read through getValues() so the diff dialog — and
  // the enabled state of the button that opens it — track what is in the
  // textareas right now, including edits that have not been saved yet.
  const descriptionValue = watch("description");
  const generatedDescriptionValue = watch("generatedDescription");

  const applyWorkflow = useCallback(
    (wf: Workflow) => {
      setWorkflow(wf);
      reset({
        name: wf.name,
        description: wf.description ?? "",
        generatedDescription: wf.generatedDescription ?? "",
      });
      setAudit({
        createdBy: wf.createdBy,
        updatedBy: wf.updatedBy,
        createdAt: wf.createdAt,
        updatedAt: wf.updatedAt,
        tenantId: isAllTenantsView ? wf.tenantId : undefined,
      });
    },
    [reset, isAllTenantsView]
  );

  useEffect(() => {
    getWorkflow(workflowId, SUPPRESS_FORBIDDEN_TOAST)
      .then(async (wf) => {
        applyWorkflow(wf);
        setTagIds(wf.tagIds ?? []);
        setSavedTagIds(wf.tagIds ?? []);
        setSkill(await getAgentSkill(wf.agentSkillId, SUPPRESS_FORBIDDEN_TOAST));
      })
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [workflowId, applyWorkflow]);

  // Design generation settles server-side with nothing to notify us, so poll
  // until the workflow leaves `generating`.
  const generating = workflow?.status === "generating";
  useEffect(() => {
    if (!generating) return;
    const timer = setInterval(() => {
      getWorkflow(workflowId)
        .then(applyWorkflow)
        .catch(() => {
          // Transient poll failure; the next tick retries.
        });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [generating, workflowId, applyWorkflow]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const updated = await updateWorkflow(workflowId, {
          name: values.name,
          description: values.description || null,
          ...(isSuperAdmin ? { generatedDescription: values.generatedDescription || null } : {}),
        });
        // Tags are a separate sub-resource, so they are only written when the
        // selection actually changed; its response is the fresher record.
        let latest = updated;
        if (!sameIds(tagIds, savedTagIds)) {
          latest = await setWorkflowTags(workflowId, tagIds);
          setSavedTagIds(tagIds);
        }
        applyWorkflow(latest);
        dispatch(showToast({ message: "Workflow updated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handlePublish() {
    setConfirmPublishOpen(false);
    try {
      await publish.run(async () => {
        const published = await publishWorkflow(workflowId);
        applyWorkflow(published);
        dispatch(showToast({ message: "Workflow published" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handleGenerateDescription() {
    try {
      await generateDescription.run(async () => {
        const updated = await generateWorkflowDescription(workflowId);
        applyWorkflow(updated);
        dispatch(showToast({ message: "Description generated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handleDiscard() {
    setConfirmDiscardOpen(false);
    try {
      await discard.run(async () => {
        const restored = await discardWorkflowChanges(workflowId);
        applyWorkflow(restored);
        dispatch(showToast({ message: "Changes discarded" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handleDeactivate() {
    setConfirmDeactivateOpen(false);
    try {
      await deactivate.run(async () => {
        const deactivated = await deactivateWorkflow(workflowId);
        applyWorkflow(deactivated);
        dispatch(showToast({ message: "Workflow deactivated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  function handleOpenDesign() {
    // A design session has no id of its own — it is addressed by its workflow.
    router.push(`/workflows/${encodeURIComponent(workflowId)}/design-session`);
  }

  async function handleRun(toolMockIds: string[]) {
    setConfirmRunOpen(false);
    try {
      await run.run(async () => {
        const workflowExecution = await executeWorkflow(workflowId, { toolMockIds });
        router.push(`/workflow-executions/${workflowExecution.id}/session`);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflow(workflowId);
      router.push("/admin/workflows");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflows", href: "/admin/workflows" },
    // The workflow itself is the current page; an ellipsis stands in until its
    // name has loaded.
    { label: workflow?.name || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !workflow) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={WorkflowIcon} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  const canDeactivate = workflow.status === "published" || workflow.status === "modified";

  // The commit shown is the workflow's own pinned revision, not the skill's
  // current one — that's the code the workflow actually runs, even after the
  // skill has been re-pulled to a newer commit.
  const skillTooltip = skill
    ? [
        `Repo URL: ${skill.repoUrl}`,
        `Ref: ${skill.repoRef || "default branch"}`,
        `Path: ${skill.repoPath || "repo root"}`,
        `Commit: ${formatRevision(workflow.agentSkillCommitSha)}`,
      ].join("\n")
    : "";

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={workflow.name}
            icon={WorkflowIcon}
            secondaryAction={
              <>
                {canEdit && (
                  <HeaderIconButton
                    label="Open design session"
                    onClick={handleOpenDesign}
                    disabled={generating}
                  >
                    <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
                  </HeaderIconButton>
                )}
                {canRun && (
                  <HeaderIconButton
                    label="Run workflow"
                    onClick={() => setConfirmRunOpen(true)}
                    disabled={
                      generating ||
                      run.inFlight ||
                      !canExecuteWorkflow(workflow.status, { canRun, canEdit })
                    }
                  >
                    {run.inFlight ? (
                      <Loader2
                        size={18}
                        strokeWidth={1.8}
                        aria-hidden="true"
                        className="motion-safe:animate-spin"
                      />
                    ) : (
                      <Play size={18} strokeWidth={1.8} aria-hidden="true" />
                    )}
                  </HeaderIconButton>
                )}
                {canViewTemplates && (
                  <HeaderIconButton
                    label={canEdit ? "Manage task templates" : "View task templates"}
                    onClick={() => router.push(`/admin/workflows/${workflowId}/task-templates`)}
                    disabled={generating}
                  >
                    <ClipboardList size={18} strokeWidth={1.8} aria-hidden="true" />
                  </HeaderIconButton>
                )}
              </>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <StatusCard
          ariaLabel="Workflow status"
          // Signature "live edge": a lifecycle transition is being written
          // server-side, or `generating` means the background design run is
          // still going, so the card carries the same travelling light the
          // chat bubbles do. Gated on the 200ms `pending` stage rather than
          // `inFlight` so a fast rejection (409 with no task templates) never
          // flashes it. Generating the description is deliberately absent:
          // it belongs to the field below, which spins its own button and
          // lights its own live edge.
          live={
            publish.status === "pending" ||
            discard.status === "pending" ||
            deactivate.status === "pending" ||
            generating
          }
          actions={
            <>
              {canEdit && workflow.status === "modified" && (
                <ActionIconButton
                  icon={Undo2}
                  label="Discard changes"
                  onClick={() => setConfirmDiscardOpen(true)}
                  disabled={discard.inFlight}
                  spinning={discard.inFlight}
                />
              )}
              {canEdit && canDeactivate && (
                <ActionIconButton
                  icon={PowerOff}
                  label="Deactivate"
                  onClick={() => setConfirmDeactivateOpen(true)}
                  disabled={deactivate.inFlight}
                  spinning={deactivate.inFlight}
                />
              )}
              {canEdit && workflow.status !== "published" && (
                <ActionIconButton
                  icon={Rocket}
                  label="Publish"
                  onClick={() => setConfirmPublishOpen(true)}
                  disabled={generating || publish.inFlight}
                  spinning={publish.inFlight}
                  spinAnimation="rocket-launch"
                />
              )}
            </>
          }
          error={workflow.status === "failed" ? workflow.generationError : null}
        >
          <StatusLine workflow={workflow} />
        </StatusCard>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="agentSkill" label="Agent Skill">
            <div className="py-1.5">
              <Tooltip label={skillTooltip} disabled={!skill}>
                <Link
                  href={`/admin/agent-skills/${workflow.agentSkillId}`}
                  className="text-sm font-medium text-accent transition-colors hover:underline"
                >
                  {skill?.name ?? workflow.agentSkillId}
                </Link>
              </Tooltip>
            </div>
          </FormField>

          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            {canEdit ? (
              <Input id="name" {...register("name")} />
            ) : (
              <ReadOnlyField>{workflow.name}</ReadOnlyField>
            )}
          </FormField>

          <FormField
            htmlFor="description"
            label="Description"
            action={
              <ActionIconButton
                icon={GitCompare}
                label="Show diff from the generated description"
                onClick={() => setDiffOpen(true)}
                // Without a generated description there is no baseline to diff
                // against, so the dialog would have nothing to show.
                disabled={generatedDescriptionValue.trim() === ""}
              />
            }
          >
            {canEdit ? (
              <Textarea
                id="description"
                rows={4}
                placeholder="Overrides the generated description below for the workflow execution"
                {...register("description")}
              />
            ) : (
              <ReadOnlyField className="whitespace-pre-wrap">
                {workflow.description || "—"}
              </ReadOnlyField>
            )}
          </FormField>

          <FormField
            htmlFor="generatedDescription"
            label="Generated description"
            action={
              canEdit ? (
                <ActionIconButton
                  icon={Sparkles}
                  label="Generate from the design conversation"
                  onClick={handleGenerateDescription}
                  // While the task templates are still generating the background job owns
                  // this field and there is no settled conversation to
                  // summarize yet.
                  disabled={generating || generateDescription.inFlight}
                  spinning={generateDescription.inFlight}
                  spinAnimation="spin-y"
                />
              ) : undefined
            }
          >
            <div
              className={["rounded-xl", generateDescription.status === "pending" ? "live-edge" : ""]
                .filter(Boolean)
                .join(" ")}
            >
              {isSuperAdmin ? (
                <Textarea
                  id="generatedDescription"
                  rows={4}
                  placeholder="Summarized from the design conversation"
                  {...register("generatedDescription")}
                />
              ) : (
                <ReadOnlyField className="whitespace-pre-wrap">
                  {workflow.generatedDescription || "—"}
                </ReadOnlyField>
              )}
            </div>
            <p className="text-xs text-on-surface-variant">
              {isSuperAdmin
                ? "AI-generated summary. Only a super admin can edit it directly."
                : "AI-generated summary, read-only."}{" "}
              Used for the workflow execution whenever Description above is empty.
            </p>
          </FormField>

          <TagPicker value={tagIds} onChange={setTagIds} readOnly={!canEdit} />

          <div className="flex flex-wrap gap-2">
            {canEdit && (
              <Button
                type="submit"
                variant="primary"
                disabled={save.inFlight}
                status={save.status}
                pendingLabel="Saving…"
              >
                Save
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/workflows")}>
              {canEdit ? "Cancel" : "Back"}
            </Button>
            {canEdit && (
              <Button
                type="button"
                variant="danger"
                onClick={() => setConfirmOpen(true)}
                className="ml-auto"
              >
                Delete
              </Button>
            )}
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Workflow"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
      <ConfirmDialog
        open={confirmDiscardOpen}
        title="Discard Changes"
        description="Restore this workflow and its task templates to the last published version? Unpublished edits are lost."
        confirmLabel="Discard"
        onConfirm={handleDiscard}
        onCancel={() => setConfirmDiscardOpen(false)}
      />
      <ConfirmDialog
        open={confirmDeactivateOpen}
        title="Deactivate Workflow"
        description="Return this workflow to draft? Only developers will be able to run it for testing until it's published again."
        confirmLabel="Deactivate"
        onConfirm={handleDeactivate}
        onCancel={() => setConfirmDeactivateOpen(false)}
      />
      <ConfirmDialog
        open={confirmPublishOpen}
        title="Publish Workflow"
        description="Publish this workflow? It becomes runnable by anyone with Run access."
        confirmLabel="Publish"
        confirmVariant="primary"
        onConfirm={handlePublish}
        onCancel={() => setConfirmPublishOpen(false)}
      />
      <RunWorkflowDialog
        open={confirmRunOpen}
        workflowId={workflowId}
        workflowName={workflow.name}
        isDraft={workflow.status === "draft"}
        onConfirm={handleRun}
        onCancel={() => setConfirmRunOpen(false)}
      />
      <DescriptionDiffDialog
        open={diffOpen}
        generated={generatedDescriptionValue}
        description={descriptionValue}
        onClose={() => setDiffOpen(false)}
      />
    </AdminPageContainer>
  );
}
