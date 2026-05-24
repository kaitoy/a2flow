/** @module WorkflowDetailPage — Admin edit/view form for an existing workflow. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  type AgentSkill,
  deleteWorkflow,
  getWorkflow,
  listAgentSkills,
  updateWorkflow,
} from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  prompt: z.string().min(1, "Prompt is required"),
  agentSkillId: z.string().min(1, "Agent skill is required"),
  description: z.string(),
});

type FormValues = z.infer<typeof schema>;

export default function EditWorkflowPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", prompt: "", agentSkillId: "", description: "" },
  });

  useEffect(() => {
    Promise.all([getWorkflow(workflowId), listAgentSkills(1000, 0)])
      .then(([workflow, skillList]) => {
        setSkills(skillList);
        reset({
          name: workflow.name,
          prompt: workflow.prompt,
          agentSkillId: workflow.agentSkillId,
          description: workflow.description ?? "",
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
      await updateWorkflow(workflowId, {
        name: values.name,
        prompt: values.prompt,
        agentSkillId: values.agentSkillId,
        description: values.description || null,
      });
      router.push("/admin/workflows");
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
      <div className="flex items-center justify-center p-16">
        <Spinner size="lg" />
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
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
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
