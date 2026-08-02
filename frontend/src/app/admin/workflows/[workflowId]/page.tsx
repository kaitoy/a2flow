/** @module WorkflowDetailPage — Admin detail page for an existing workflow and its plan. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  ListTree,
  MessageSquareText,
  PowerOff,
  Rocket,
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
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deactivateWorkflow,
  deleteWorkflow,
  discardWorkflowChanges,
  getAgentSkill,
  getWorkflow,
  getWorkflowPlanningSession,
  publishWorkflow,
  updateWorkflow,
  type Workflow,
  type WorkflowStatus,
} from "@/lib/api";
import { formatWorkflowStatusLabel, WORKFLOW_STATUS_DOT_CLASS } from "@/lib/workflow-status";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How often (ms) to re-fetch the workflow while its plan is still generating. */
const POLL_INTERVAL_MS = 2000;

// Only name and description are client-writable; reuse the generated name
// constraint and allow a free-form (bounded) description.
const schema = z.object({
  name: zGenerateWorkflowRequest.shape.name,
  description: z.string().max(2000),
});

type FormValues = z.infer<typeof schema>;

/** Status dot plus label for the workflow's lifecycle state. */
function StatusLine({ workflow }: { workflow: Workflow }) {
  const status = (workflow.status ?? "draft") as WorkflowStatus;
  return (
    <span className="flex items-center gap-2">
      <span
        className={`inline-block size-2 rounded-full ${WORKFLOW_STATUS_DOT_CLASS[status]}`}
        aria-hidden
      />
      <span className="capitalize">{formatWorkflowStatusLabel(status)}</span>
    </span>
  );
}

/**
 * Detail page of a generated workflow, titled with the workflow's own name:
 * edit name/description, watch the plan generation settle, open the planning
 * session to adjust the plan by chat, manage the task templates, and publish
 * the workflow to make it executable.
 *
 * Editing a published workflow moves it to `modified` — runs keep using the
 * last published version — so the status bar then also offers "Discard
 * changes", which restores that version and returns the workflow to
 * `published`. A `published`/`modified` workflow can also be "Deactivated"
 * back to `draft`, revoking `requester` execute access until it is published
 * again.
 */
export default function WorkflowDetailPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [skillName, setSkillName] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false);
  const [confirmDeactivateOpen, setConfirmDeactivateOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const publish = useAsyncAction({ showDone: false });
  const discard = useAsyncAction({ showDone: false });
  const deactivate = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", description: "" },
  });

  const applyWorkflow = useCallback(
    (wf: Workflow) => {
      setWorkflow(wf);
      reset({ name: wf.name, description: wf.description ?? "" });
      setAudit({
        createdBy: wf.createdBy,
        updatedBy: wf.updatedBy,
        createdAt: wf.createdAt,
        updatedAt: wf.updatedAt,
      });
    },
    [reset]
  );

  useEffect(() => {
    getWorkflow(workflowId)
      .then(async (wf) => {
        applyWorkflow(wf);
        setSkillName((await getAgentSkill(wf.agentSkillId)).name);
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [workflowId, applyWorkflow]);

  // Plan generation settles server-side with nothing to notify us, so poll
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
        });
        applyWorkflow(updated);
        dispatch(showToast({ message: "Workflow updated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function handlePublish() {
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

  async function handleOpenPlanning() {
    try {
      const ps = await getWorkflowPlanningSession(workflowId);
      router.push(`/planning-sessions/${ps.id}`);
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

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={workflow.name}
            icon={WorkflowIcon}
            secondaryAction={
              <HeaderIconButton
                label="Open planning session"
                onClick={handleOpenPlanning}
                disabled={generating}
              >
                <MessageSquareText size={18} strokeWidth={1.8} aria-hidden="true" />
              </HeaderIconButton>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <section
          aria-label="Workflow status"
          className={[
            "mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl glass-panel p-4",
            // Signature "live edge": publishing runs the description summarizer
            // synchronously and `generating` means the background planning run
            // is still going — both are the agent at work, so the card carries
            // the same travelling light the chat bubbles do. Gated on the
            // 200ms `pending` stage rather than `inFlight` so a fast rejection
            // (409 with no task templates) never flashes it.
            publish.status === "pending" ||
            discard.status === "pending" ||
            deactivate.status === "pending" ||
            generating
              ? "live-edge"
              : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <StatusLine workflow={workflow} />
          <div className="ml-auto flex items-center gap-2">
            {workflow.status === "modified" && (
              <ActionIconButton
                icon={Undo2}
                label="Discard changes"
                onClick={() => setConfirmDiscardOpen(true)}
                disabled={discard.inFlight}
                spinning={discard.inFlight}
              />
            )}
            {canDeactivate && (
              <ActionIconButton
                icon={PowerOff}
                label="Deactivate"
                onClick={() => setConfirmDeactivateOpen(true)}
                disabled={deactivate.inFlight}
                spinning={deactivate.inFlight}
              />
            )}
            <ActionIconButton
              icon={Rocket}
              label="Publish"
              onClick={handlePublish}
              disabled={generating || publish.inFlight}
              spinning={publish.inFlight}
              spinAnimation="rocket-launch"
            />
          </div>
          {workflow.status === "failed" && workflow.generationError && (
            <p className="w-full break-words font-mono text-error text-xs">
              {workflow.generationError}
            </p>
          )}
        </section>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="agentSkill" label="Agent Skill">
            <div className="py-1.5">
              <Link
                href={`/admin/agent-skills/${workflow.agentSkillId}`}
                className="text-sm font-medium text-accent transition-colors hover:underline"
              >
                {skillName ?? workflow.agentSkillId}
              </Link>
            </div>
          </FormField>

          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" {...register("name")} />
          </FormField>

          <FormField htmlFor="description" label="Description">
            <Textarea
              id="description"
              rows={4}
              placeholder="Summarized from the planning conversation on publish"
              {...register("description")}
            />
          </FormField>

          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/workflows")}>
              Cancel
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
        </form>

        <div className="mt-4 flex items-center justify-between rounded-2xl glass-panel-strong p-4">
          <div className="flex items-center gap-2 text-sm text-on-surface">
            <ListTree size={16} strokeWidth={1.8} aria-hidden="true" />
            Task templates — the plan copied into every run of this workflow.
          </div>
          <Link
            href={`/admin/workflows/${workflowId}/task-templates`}
            className="text-sm font-medium text-accent transition-colors hover:underline"
          >
            Manage templates
          </Link>
        </div>
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
    </AdminPageContainer>
  );
}
