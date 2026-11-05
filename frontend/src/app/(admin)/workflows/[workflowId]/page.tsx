/** @module WorkflowDetailPage — Admin detail page for an existing workflow and its task templates. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  ClipboardList,
  GitCompare,
  History,
  Loader2,
  MessageSquareText,
  Play,
  PowerOff,
  Rocket,
  Save,
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
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { KnowledgeBasePicker } from "@/components/admin/knowledge-base-picker";
import { PromptDiffDialog } from "@/components/admin/prompt-diff-dialog";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { type RunWorkflowChoice, RunWorkflowDialog } from "@/components/admin/run-workflow-dialog";
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
import { useT } from "@/i18n/provider";
import { formatRevision } from "@/lib/agent-skill-sync-status";
import {
  type AgentSkill,
  deactivateWorkflow,
  deleteWorkflow,
  discardWorkflowChanges,
  executeWorkflow,
  generateWorkflowPrompt,
  getAgentSkill,
  getWorkflow,
  isForbiddenError,
  listWorkflowKnowledgeBases,
  publishWorkflow,
  SUPPRESS_FORBIDDEN_TOAST,
  setWorkflowInternalNotes,
  setWorkflowKnowledgeBases,
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

// name, description, and prompt are client-writable by any developer; reuse
// the generated name constraint and allow free-form (bounded) text.
// generatedPrompt is only ever submitted for a super_admin caller (see
// isSuperAdmin below), but stays part of the schema so register()/reset() can
// address it regardless of role.
const schema = z.object({
  name: zGenerateWorkflowRequest.shape.name,
  description: z.string().max(2000),
  prompt: z.string().max(10000),
  generatedPrompt: z.string().max(10000),
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
 * edit name/description/prompt, watch the design run settle, open the design
 * session to adjust the task templates by chat, run the workflow, manage the task
 * templates, and publish the workflow to make it executable.
 *
 * The header's Run button follows the same `canExecuteWorkflow` rule as the
 * workflows list — hidden for viewers who can't execute workflows at all, and
 * disabled for a `draft` workflow unless the viewer can also edit workflows
 * (pre-publish testing) — and, on success, navigates to the new run's
 * `WorkflowExecution` page just like the list's Run action.
 *
 * `description` is plain prose explaining the workflow to people; no run ever
 * reads it. `prompt` is what a run is told: a free-form field any developer
 * can set, falling back to the AI-generated `generatedPrompt` whenever it's
 * empty. `generatedPrompt` itself is read-only for everyone except a
 * super admin, who can edit it directly to correct the AI's summary. Any
 * developer can instead re-derive it from the design conversation through
 * the field's own generate button, which saves the new summary server-side
 * right away (and so moves a published workflow to `modified`). Since the
 * override is usually a hand-edit of that summary, the Prompt field also
 * carries a button opening a word-level diff of the two current (possibly
 * unsaved) values. Both prompt fields are shown only to an admin, developer,
 * or reviewer — the backend blanks them for everyone else.
 *
 * Internal notes follow the same visibility rule: a scratchpad for those three
 * roles (why a version was restored, say). They are not part of the design, so
 * any of the three can save them on the spot through the field's own save
 * button, which never moves a published workflow to `modified`; the form's
 * Save also writes them when they changed, so a developer's typed notes are not
 * lost on submit. The Version history button is shown to the same three roles
 * too — the backend refuses the history to a requester or approver.
 *
 * Editing a published workflow moves it to `modified` — runs keep using the
 * last published version — so the status bar then also offers "Discard
 * changes", which restores that version and returns the workflow to
 * `published`. The Run dialog then also offers a choice between the two
 * designs: the published version as a real request, or the unpublished edits
 * as a test run. A `published`/`modified` workflow can also be "Deactivated"
 * back to `draft`, revoking `requester` execute access until it is published
 * again.
 *
 * Publishing and deactivating are `reviewer` actions, not `developer` ones —
 * the two roles have disjoint write access to a workflow but the same read
 * visibility. A `developer` sees and edits the live design (including a
 * `modified` workflow's unpublished edits) but no longer has Publish or
 * Deactivate buttons; a `reviewer` sees the exact same live design — enough to
 * decide whether it's ready — and gets Publish/Deactivate instead, with every
 * editing action hidden.
 *
 * Neither the live design nor `modified` reaches anyone else: the backend
 * serves a plain viewer (e.g. `requester`) a `modified` workflow as
 * `published`, carrying its last published name, description, prompt, and task
 * templates. So this page never has to hide the edits itself for them — it
 * simply never receives them.
 *
 * A viewer who cannot edit (`requester`, or a `reviewer` who cannot edit
 * either) gets a read-only rendering: Name and Description show as plain
 * text, and every action that would hit a developer-only endpoint — Open
 * design session (for driving it), Discard changes, Save, Delete — is hidden
 * rather than left to fail with a 403 on click. Task templates and the design
 * session's chat history stay reachable read-only for a `developer` or
 * `reviewer` — the header button is labeled "View task templates" (or "View
 * design session") instead of "Manage"/"Open" for whichever of the two they
 * lack, and the templates screens it opens hide their own write actions the
 * same way. The "Workflow status" bar itself stays visible for every viewer —
 * the status is useful context regardless of role — but Discard changes
 * (developer-only) and Deactivate/Publish (reviewer-only) are hidden
 * individually the same way as elsewhere on the page.
 */
export default function WorkflowDetailPage() {
  const t = useT();
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  const canRun = useHasRole(Role.REQUESTER, Role.DEVELOPER);
  const canEdit = useHasRole(Role.DEVELOPER);
  const canPublish = useHasRole(Role.REVIEWER);
  const canViewDesign = useHasRole(Role.DEVELOPER, Role.REVIEWER);
  const canViewTemplates = useHasRole(Role.REQUESTER, Role.DEVELOPER, Role.REVIEWER);
  const canViewPrompt = useHasRole(Role.ADMIN, Role.DEVELOPER, Role.REVIEWER);
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
  // The knowledge bases the workflow's agents may read: a sub-resource like
  // tags, and kept out of `applyWorkflow` for the same reason.
  const [kbIds, setKbIds] = useState<string[]>([]);
  const [savedKbIds, setSavedKbIds] = useState<string[]>([]);
  const [kbOptions, setKbOptions] = useState<PickerOption[]>([]);
  // Internal notes are saved through their own route and, like tags, kept out
  // of `applyWorkflow` so a generation poll never clobbers an in-progress edit.
  const [notes, setNotes] = useState("");
  const [savedNotes, setSavedNotes] = useState("");

  const save = useAsyncAction({ showDone: false });
  const publish = useAsyncAction({ showDone: false });
  const discard = useAsyncAction({ showDone: false });
  const deactivate = useAsyncAction({ showDone: false });
  const run = useAsyncAction({ showDone: false });
  const generatePrompt = useAsyncAction({ showDone: false });
  const saveNotes = useAsyncAction({ showDone: false });
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
    defaultValues: { name: "", description: "", prompt: "", generatedPrompt: "" },
  });

  // Subscribed rather than read through getValues() so the diff dialog — and
  // the enabled state of the button that opens it — track what is in the
  // textareas right now, including edits that have not been saved yet.
  const promptValue = watch("prompt");
  const generatedPromptValue = watch("generatedPrompt");

  const applyWorkflow = useCallback(
    (wf: Workflow) => {
      setWorkflow(wf);
      reset({
        name: wf.name,
        description: wf.description ?? "",
        prompt: wf.prompt ?? "",
        generatedPrompt: wf.generatedPrompt ?? "",
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
        setNotes(wf.internalNotes ?? "");
        setSavedNotes(wf.internalNotes ?? "");
        listWorkflowKnowledgeBases(workflowId)
          .then((kbs) => {
            const ids = kbs.map((kb) => kb.id);
            setKbIds(ids);
            setSavedKbIds(ids);
            setKbOptions(kbs.map((kb) => ({ value: kb.id, label: kb.name })));
          })
          .catch(() => {
            // Failure toast is shown globally by api.ts; the picker starts empty.
          });
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
        await updateWorkflow(workflowId, {
          name: values.name,
          description: values.description || null,
          prompt: values.prompt || null,
          ...(isSuperAdmin ? { generatedPrompt: values.generatedPrompt || null } : {}),
        });
        // Tags are a separate sub-resource, so they are only written when the
        // selection actually changed.
        if (!sameIds(tagIds, savedTagIds)) {
          await setWorkflowTags(workflowId, tagIds);
        }
        if (!sameIds(kbIds, savedKbIds)) {
          await setWorkflowKnowledgeBases(workflowId, kbIds);
        }
        if (notes !== savedNotes) {
          await setWorkflowInternalNotes(workflowId, notes);
        }
        dispatch(showToast({ message: t("workflows.workflowUpdated") }));
        // Return to the list on success, matching every other admin edit page.
        router.push("/workflows");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handleSaveNotes() {
    try {
      await saveNotes.run(async () => {
        const updated = await setWorkflowInternalNotes(workflowId, notes);
        setSavedNotes(updated.internalNotes ?? "");
        dispatch(showToast({ message: t("workflows.internalNotesSaved") }));
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
        dispatch(showToast({ message: t("workflows.workflowPublished") }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handleGeneratePrompt() {
    try {
      await generatePrompt.run(async () => {
        const updated = await generateWorkflowPrompt(workflowId);
        applyWorkflow(updated);
        dispatch(showToast({ message: t("workflows.promptGenerated") }));
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
        dispatch(showToast({ message: t("workflows.changesDiscarded") }));
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
        dispatch(showToast({ message: t("workflows.workflowDeactivated") }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  function handleOpenDesign() {
    // A design session has no id of its own — it is addressed by its workflow.
    router.push(`/workflows/${encodeURIComponent(workflowId)}/design-session`);
  }

  async function handleRun({ designSource, toolMockIds }: RunWorkflowChoice) {
    setConfirmRunOpen(false);
    try {
      await run.run(async () => {
        const workflowExecution = await executeWorkflow(workflowId, {
          designSource,
          toolMockIds,
        });
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
      router.push("/workflows");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.workflows"), href: "/workflows" },
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
                {canViewDesign && (
                  <HeaderIconButton
                    label={
                      canEdit ? t("workflows.openDesignSession") : t("workflows.viewDesignSession")
                    }
                    onClick={handleOpenDesign}
                    disabled={generating}
                  >
                    <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
                  </HeaderIconButton>
                )}
                {canRun && (
                  <HeaderIconButton
                    label={t("workflows.runWorkflow")}
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
                    label={
                      canEdit
                        ? t("workflows.manageTaskTemplates")
                        : t("workflows.viewTaskTemplates")
                    }
                    onClick={() => router.push(`/workflows/${workflowId}/task-templates`)}
                    disabled={generating}
                  >
                    <ClipboardList size={18} strokeWidth={1.8} aria-hidden="true" />
                  </HeaderIconButton>
                )}
                {canViewPrompt && (
                  <HeaderIconButton
                    label={t("workflows.versionHistory")}
                    onClick={() => router.push(`/workflows/${workflowId}/versions`)}
                    disabled={generating}
                  >
                    <History size={18} strokeWidth={1.8} aria-hidden="true" />
                  </HeaderIconButton>
                )}
              </>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <StatusCard
          ariaLabel={t("workflows.workflowStatus")}
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
                  label={t("workflows.discardChanges")}
                  onClick={() => setConfirmDiscardOpen(true)}
                  disabled={discard.inFlight}
                  spinning={discard.inFlight}
                />
              )}
              {canPublish && canDeactivate && (
                <ActionIconButton
                  icon={PowerOff}
                  label={t("workflows.deactivate")}
                  onClick={() => setConfirmDeactivateOpen(true)}
                  disabled={deactivate.inFlight}
                  spinning={deactivate.inFlight}
                />
              )}
              {canPublish && workflow.status !== "published" && (
                <ActionIconButton
                  icon={Rocket}
                  label={t("workflows.publish")}
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
          <FormField htmlFor="name" label={t("common.name")} required error={errors.name?.message}>
            {canEdit ? (
              <Input id="name" {...register("name")} />
            ) : (
              <ReadOnlyField>{workflow.name}</ReadOnlyField>
            )}
          </FormField>

          <FormField htmlFor="agentSkill" label={t("common.agentSkill")}>
            <div className="py-1.5">
              <Tooltip label={skillTooltip} disabled={!skill}>
                <Link
                  href={`/agent-skills/${workflow.agentSkillId}`}
                  className="text-sm font-medium text-accent transition-colors hover:underline"
                >
                  {skill?.name ?? workflow.agentSkillId}
                </Link>
              </Tooltip>
            </div>
          </FormField>

          <FormField
            htmlFor="description"
            label={t("common.description")}
            error={errors.description?.message}
          >
            {canEdit ? (
              <Textarea
                id="description"
                rows={3}
                placeholder={t("workflows.whatThisWorkflowIsForNotUsed")}
                {...register("description")}
              />
            ) : (
              <ReadOnlyField className="whitespace-pre-wrap">
                {workflow.description || "—"}
              </ReadOnlyField>
            )}
          </FormField>

          {canViewPrompt && (
            <FormField
              htmlFor="prompt"
              label={t("common.prompt")}
              action={
                <ActionIconButton
                  icon={GitCompare}
                  label={t("workflows.showDiffFromTheGeneratedPrompt")}
                  onClick={() => setDiffOpen(true)}
                  // Without a generated prompt there is no baseline to diff
                  // against, so the dialog would have nothing to show.
                  disabled={generatedPromptValue.trim() === ""}
                />
              }
            >
              {canEdit ? (
                <Textarea
                  id="prompt"
                  rows={4}
                  placeholder={t("workflows.overridesTheGeneratedPromptBelowForThe")}
                  {...register("prompt")}
                />
              ) : (
                <ReadOnlyField className="whitespace-pre-wrap">
                  {workflow.prompt || "—"}
                </ReadOnlyField>
              )}
            </FormField>
          )}

          {canViewPrompt && (
            <FormField
              htmlFor="generatedPrompt"
              label={t("workflows.generatedPrompt")}
              action={
                canEdit ? (
                  <ActionIconButton
                    icon={Sparkles}
                    label={t("workflows.generateFromTheDesignConversation")}
                    onClick={handleGeneratePrompt}
                    // While the task templates are still generating the background job owns
                    // this field and there is no settled conversation to
                    // summarize yet.
                    disabled={generating || generatePrompt.inFlight}
                    spinning={generatePrompt.inFlight}
                    spinAnimation="spin-y"
                  />
                ) : undefined
              }
            >
              <div
                className={["rounded-xl", generatePrompt.status === "pending" ? "live-edge" : ""]
                  .filter(Boolean)
                  .join(" ")}
              >
                {isSuperAdmin ? (
                  <Textarea
                    id="generatedPrompt"
                    rows={4}
                    placeholder={t("workflows.summarizedFromTheDesignConversation")}
                    {...register("generatedPrompt")}
                  />
                ) : (
                  <ReadOnlyField className="whitespace-pre-wrap">
                    {workflow.generatedPrompt || "—"}
                  </ReadOnlyField>
                )}
              </div>
              <p className="text-xs text-on-surface-variant">
                {isSuperAdmin
                  ? t("workflows.aiGeneratedSummaryOnlyASuperAdmin")
                  : t("workflows.aiGeneratedSummaryReadOnly")}{" "}
                {t("workflows.usedForTheWorkflowExecutionWheneverPrompt")}
              </p>
            </FormField>
          )}

          <KnowledgeBasePicker
            value={kbIds}
            onChange={setKbIds}
            readOnly={!canEdit}
            initialOptions={kbOptions}
          />

          <TagPicker value={tagIds} onChange={setTagIds} readOnly={!canEdit} />

          {canViewPrompt && (
            <FormField
              htmlFor="internalNotes"
              label={t("workflows.internalNotes")}
              action={
                <ActionIconButton
                  icon={Save}
                  label={t("workflows.saveInternalNotes")}
                  onClick={handleSaveNotes}
                  disabled={notes === savedNotes || saveNotes.inFlight}
                  spinning={saveNotes.inFlight}
                />
              }
            >
              <Textarea
                id="internalNotes"
                rows={3}
                maxLength={10000}
                placeholder={t("workflows.eGWhyAVersionWasRestored")}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <p className="text-xs text-on-surface-variant">
                {t("workflows.visibleOnlyToAdminsDevelopersAndReviewers")}
              </p>
            </FormField>
          )}

          <div className="flex flex-wrap gap-2">
            {canEdit && (
              <Button
                type="submit"
                variant="primary"
                disabled={save.inFlight}
                status={save.status}
                pendingLabel={t("common.saving")}
              >
                {t("common.save")}
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={() => router.push("/workflows")}>
              {canEdit ? t("common.cancel") : t("common.back")}
            </Button>
            {canEdit && (
              <Button
                type="button"
                variant="danger"
                onClick={() => setConfirmOpen(true)}
                className="ml-auto"
              >
                {t("common.delete")}
              </Button>
            )}
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title={t("workflows.deleteWorkflow")}
        description={t("common.deleteValue", { value: getValues("name") })}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
      <ConfirmDialog
        open={confirmDiscardOpen}
        title={t("workflows.discardChanges2")}
        description={t("workflows.restoreThisWorkflowAndItsTaskTemplates")}
        confirmLabel={t("workflows.discard")}
        onConfirm={handleDiscard}
        onCancel={() => setConfirmDiscardOpen(false)}
      />
      <ConfirmDialog
        open={confirmDeactivateOpen}
        title={t("workflows.deactivateWorkflow")}
        description={t("workflows.returnThisWorkflowToDraftOnlyDevelopers")}
        confirmLabel={t("workflows.deactivate")}
        onConfirm={handleDeactivate}
        onCancel={() => setConfirmDeactivateOpen(false)}
      />
      <ConfirmDialog
        open={confirmPublishOpen}
        title={t("workflows.publishWorkflow")}
        description={t("workflows.publishThisWorkflowItBecomesRunnableBy")}
        confirmLabel={t("workflows.publish")}
        confirmVariant="primary"
        onConfirm={handlePublish}
        onCancel={() => setConfirmPublishOpen(false)}
      />
      <RunWorkflowDialog
        open={confirmRunOpen}
        workflowId={workflowId}
        workflowName={workflow.name}
        workflowDescription={workflow.description}
        isDraft={workflow.status === "draft"}
        // Only a developer ever sees `modified` — for everyone else the backend
        // reports the workflow as `published` — so the status alone is the gate.
        canChooseDesign={workflow.status === "modified" && canEdit}
        onConfirm={handleRun}
        onCancel={() => setConfirmRunOpen(false)}
      />
      <PromptDiffDialog
        open={diffOpen}
        generated={generatedPromptValue}
        prompt={promptValue}
        onClose={() => setDiffOpen(false)}
      />
    </AdminPageContainer>
  );
}
