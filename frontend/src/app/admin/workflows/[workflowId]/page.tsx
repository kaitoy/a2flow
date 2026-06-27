/** @module WorkflowDetailPage — Admin edit/view form for an existing workflow. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  type AgentSkill,
  deleteWorkflow,
  getWorkflow,
  listAgentSkills,
  updateWorkflow,
} from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries name/prompt/description constraints; tighten the
// agentSkillId foreign key to a required selection for the form's dropdown.
const schema = zWorkflowCreate.extend({
  agentSkillId: z.string().min(1, "Agent skill is required"),
});

type FormValues = z.infer<typeof schema>;

export default function EditWorkflowPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", prompt: "", agentSkillId: "", description: "" },
  });

  useEffect(() => {
    Promise.all([getWorkflow(workflowId), listAgentSkills({ limit: 1000 })])
      .then(([workflow, skillList]) => {
        setSkills(skillList);
        reset({
          name: workflow.name,
          prompt: workflow.prompt,
          agentSkillId: workflow.agentSkillId,
          description: workflow.description ?? "",
        });
        setAudit({
          createdBy: workflow.createdBy,
          updatedBy: workflow.updatedBy,
          createdAt: workflow.createdAt,
          updatedAt: workflow.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load workflow");
      })
      .finally(() => setLoading(false));
  }, [workflowId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await updateWorkflow(workflowId, {
          name: values.name,
          prompt: values.prompt,
          agentSkillId: values.agentSkillId,
          description: values.description || null,
        });
        dispatch(showToast({ message: "Workflow updated" }));
        router.push("/admin/workflows");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update workflow");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
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

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
          Edit Workflow
        </h1>
        <FormSkeleton fields={4} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        Edit Workflow
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
          <Input id="name" {...register("name")} />
        </FormField>

        <FormField
          htmlFor="agentSkillId"
          label="Agent Skill"
          required
          error={errors.agentSkillId?.message}
        >
          <Select id="agentSkillId" {...register("agentSkillId")}>
            <option value="">— Select a skill —</option>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField htmlFor="prompt" label="Prompt" required error={errors.prompt?.message}>
          <Textarea id="prompt" rows={6} {...register("prompt")} />
        </FormField>

        <FormField htmlFor="description" label="Description">
          <Textarea id="description" rows={3} {...register("description")} />
        </FormField>

        <ErrorBanner error={apiError} />

        <div className="flex gap-2">
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
            variant="secondary"
            onClick={handleDelete}
            className="ml-auto text-error"
          >
            Delete
          </Button>
        </div>
      </form>
      {audit && (
        <div className="mt-4">
          <AuditMeta {...audit} />
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Workflow"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
