/** @module WorkflowDetailPage — Admin edit/view form for an existing workflow and its plan. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ListTree, MessageSquareText, Rocket, Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteWorkflow,
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
 * Detail page of a generated workflow: edit name/description, watch the plan
 * generation settle, open the planning session to adjust the plan by chat,
 * manage the task templates, and publish the workflow to make it executable.
 */
export default function EditWorkflowPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [skillName, setSkillName] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const publish = useAsyncAction({ showDone: false });
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
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load workflow");
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
    setApiError(null);
    try {
      await save.run(async () => {
        const updated = await updateWorkflow(workflowId, {
          name: values.name,
          description: values.description || null,
        });
        applyWorkflow(updated);
        dispatch(showToast({ message: "Workflow updated" }));
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update workflow");
    }
  }

  async function handlePublish() {
    setApiError(null);
    try {
      await publish.run(async () => {
        const published = await publishWorkflow(workflowId);
        applyWorkflow(published);
        dispatch(showToast({ message: "Workflow published" }));
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to publish workflow");
    }
  }

  async function handleOpenPlanning() {
    setApiError(null);
    try {
      const ps = await getWorkflowPlanningSession(workflowId);
      router.push(`/planning-sessions/${ps.id}`);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to open planning session");
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflow(workflowId);
      router.push("/admin/workflows");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete workflow");
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflows", href: "/admin/workflows" },
    { label: "Edit" },
  ];

  if (loading || !workflow) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit Workflow" icon={WorkflowIcon} />
        <FormColumn>
          <FormSkeleton fields={4} />
          <ErrorBanner error={apiError} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit Workflow" icon={WorkflowIcon} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="status" label="Status">
            <div className="flex items-center gap-4 py-1.5">
              <StatusLine workflow={workflow} />
              {workflow.status === "failed" && workflow.generationError && (
                <span className="text-sm text-error">{workflow.generationError}</span>
              )}
            </div>
          </FormField>

          <FormField htmlFor="agentSkill" label="Agent Skill">
            <div className="py-1.5 text-sm text-on-surface">
              {skillName ?? workflow.agentSkillId}
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

          <ErrorBanner error={apiError} />

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
            <Button
              type="button"
              variant="secondary"
              onClick={handleOpenPlanning}
              disabled={generating}
            >
              <MessageSquareText size={16} strokeWidth={1.8} aria-hidden="true" />
              Open planning session
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handlePublish}
              disabled={generating || publish.inFlight}
              status={publish.status}
              pendingLabel="Publishing…"
            >
              <Rocket size={16} strokeWidth={1.8} aria-hidden="true" />
              Publish
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

        {audit && (
          <div className="mt-4">
            <AuditMeta {...audit} />
          </div>
        )}
      </FormColumn>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Workflow"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
